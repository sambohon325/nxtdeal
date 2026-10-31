"""
Tests for core/entity_menu_links.py -- turns a list of chat-resolved entities into a
real, capped, de-duplicated set of "deep link to the right dashboard" suggestions
(session 76), off a static entity_type -> real Top Menu (department, item_key)
mapping. An entity type with no mapping (Document, Campaign, etc.) is silently
skipped, never an error. A query-capable link (today: only Vehicle -> Operations
"vehicles", matched against VIN) resolves a real `query` value off the entity's own
attributes; a non-query-capable link never carries one.

A pure function module -- no ledger, no persistence, no monkeypatching needed.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import entity_menu_links
from core.entity_types import LEAD, CUSTOMER, VEHICLE, DEAL, FINANCE_CONTRACT, SERVICE_RECORD


def _entity(entity_id, entity_type, **attrs):
    return {"id": entity_id, "entity_type": entity_type, "attributes": attrs}


class TestBuildSuggestedActionsSingleEntityTypes:

    def test_lead_produces_a_real_sales_prospects_suggestion(self):
        result = entity_menu_links.build_suggested_actions([_entity("LEAD-1", LEAD)])

        assert len(result) == 1
        assert result[0]["entity_id"] == "LEAD-1"
        assert result[0]["entity_type"] == LEAD
        assert result[0]["department"] == "Sales"
        assert result[0]["item_key"] == "prospects"
        assert result[0]["query_capable"] is False
        assert "query" not in result[0]

    def test_customer_produces_a_real_sales_customers_suggestion(self):
        result = entity_menu_links.build_suggested_actions([_entity("CUST-1", CUSTOMER)])

        assert len(result) == 1
        assert result[0]["department"] == "Sales"
        assert result[0]["item_key"] == "customers"

    def test_deal_produces_a_real_finance_deals_suggestion(self):
        result = entity_menu_links.build_suggested_actions([_entity("DEAL-1", DEAL)])

        assert len(result) == 1
        assert result[0]["department"] == "Finance"
        assert result[0]["item_key"] == "deals"

    def test_finance_contract_produces_a_real_finance_funding_suggestion(self):
        result = entity_menu_links.build_suggested_actions([_entity("FIN-1", FINANCE_CONTRACT)])

        assert len(result) == 1
        assert result[0]["department"] == "Finance"
        assert result[0]["item_key"] == "funding"

    def test_service_record_produces_a_real_service_repair_orders_suggestion(self):
        result = entity_menu_links.build_suggested_actions([_entity("SRV-1", SERVICE_RECORD)])

        assert len(result) == 1
        assert result[0]["department"] == "Service"
        assert result[0]["item_key"] == "repair_orders"

    def test_vehicle_produces_two_real_suggestions_operations_and_inventory(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN="1FTFW1ET1EFA12345")])

        assert len(result) == 2
        departments = {(a["department"], a["item_key"]) for a in result}
        assert departments == {("Operations", "vehicles"), ("Inventory", "inventory")}


class TestQueryCapableResolution:

    def test_vehicle_operations_link_resolves_a_real_query_from_the_vin_attribute(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN="1FTFW1ET1EFA12345")])

        ops_link = next(a for a in result if a["department"] == "Operations")
        assert ops_link["query_capable"] is True
        assert ops_link["query"] == "1FTFW1ET1EFA12345"

    def test_missing_vin_attribute_resolves_query_to_none(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE)])

        ops_link = next(a for a in result if a["department"] == "Operations")
        assert ops_link["query"] is None

    def test_empty_string_vin_attribute_resolves_query_to_none(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN="")])

        ops_link = next(a for a in result if a["department"] == "Operations")
        assert ops_link["query"] is None

    def test_non_query_capable_link_never_carries_a_query_key(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN="1FT123")])

        inv_link = next(a for a in result if a["department"] == "Inventory")
        assert "query" not in inv_link

    def test_query_value_is_coerced_to_a_string(self):
        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN=12345)])

        ops_link = next(a for a in result if a["department"] == "Operations")
        assert ops_link["query"] == "12345"


class TestUnmappedAndMissingEntityTypes:

    def test_an_entity_type_with_no_mapping_is_silently_skipped(self):
        result = entity_menu_links.build_suggested_actions([_entity("DOC-1", "Document")])

        assert result == []

    def test_missing_entity_type_key_is_silently_skipped(self):
        result = entity_menu_links.build_suggested_actions([{"id": "X-1", "attributes": {}}])

        assert result == []

    def test_empty_input_list_returns_an_empty_list(self):
        assert entity_menu_links.build_suggested_actions([]) == []

    def test_missing_attributes_key_does_not_raise(self):
        result = entity_menu_links.build_suggested_actions([{"id": "VEH-1", "entity_type": VEHICLE}])

        ops_link = next(a for a in result if a["department"] == "Operations")
        assert ops_link["query"] is None

    def test_a_mix_of_mapped_and_unmapped_entities_only_returns_mapped_suggestions(self):
        result = entity_menu_links.build_suggested_actions(
            [_entity("DOC-1", "Document"), _entity("LEAD-1", LEAD), _entity("CAMP-1", "Campaign")]
        )

        assert len(result) == 1
        assert result[0]["entity_id"] == "LEAD-1"


class TestDeduplication:

    def test_the_same_entity_appearing_twice_only_produces_one_suggestion_set(self):
        result = entity_menu_links.build_suggested_actions(
            [_entity("LEAD-1", LEAD), _entity("LEAD-1", LEAD)]
        )

        assert len(result) == 1

    def test_two_different_entities_of_the_same_type_both_produce_suggestions(self):
        result = entity_menu_links.build_suggested_actions(
            [_entity("LEAD-1", LEAD), _entity("LEAD-2", LEAD)]
        )

        assert len(result) == 2
        ids = {a["entity_id"] for a in result}
        assert ids == {"LEAD-1", "LEAD-2"}


class TestMaxSuggestedActionsCap:

    def test_the_result_is_capped_at_max_suggested_actions(self):
        entities = [_entity(f"LEAD-{i}", LEAD) for i in range(10)]

        result = entity_menu_links.build_suggested_actions(entities)

        assert len(result) == entity_menu_links.MAX_SUGGESTED_ACTIONS

    def test_a_multi_link_entity_type_can_be_truncated_mid_entity_by_the_cap(self, monkeypatch):
        monkeypatch.setattr(entity_menu_links, "MAX_SUGGESTED_ACTIONS", 1)

        result = entity_menu_links.build_suggested_actions([_entity("VEH-1", VEHICLE, VIN="1FT123")])

        assert len(result) == 1
        assert result[0]["department"] == "Operations"

    def test_exactly_at_the_cap_returns_all_suggestions(self):
        entities = [_entity(f"LEAD-{i}", LEAD) for i in range(entity_menu_links.MAX_SUGGESTED_ACTIONS)]

        result = entity_menu_links.build_suggested_actions(entities)

        assert len(result) == entity_menu_links.MAX_SUGGESTED_ACTIONS

    def test_one_under_the_cap_returns_every_suggestion(self):
        entities = [_entity(f"LEAD-{i}", LEAD) for i in range(entity_menu_links.MAX_SUGGESTED_ACTIONS - 1)]

        result = entity_menu_links.build_suggested_actions(entities)

        assert len(result) == entity_menu_links.MAX_SUGGESTED_ACTIONS - 1


class TestLabelsAreRealAndPresent:

    def test_every_suggestion_carries_a_real_non_empty_label(self):
        entities = [
            _entity("LEAD-1", LEAD),
            _entity("CUST-1", CUSTOMER),
            _entity("VEH-1", VEHICLE),
            _entity("DEAL-1", DEAL),
            _entity("FIN-1", FINANCE_CONTRACT),
            _entity("SRV-1", SERVICE_RECORD),
        ]

        result = entity_menu_links.build_suggested_actions(entities)

        for action in result:
            assert isinstance(action["label"], str)
            assert len(action["label"]) > 0
