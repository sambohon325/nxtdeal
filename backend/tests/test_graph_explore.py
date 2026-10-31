"""
Tests for core/graph_explore.py / core/graph_explore_api.py -- generic, role-gated
multi-hop graph traversal (session 76 fourth follow-up). Run from backend/ with
`pytest`.

Covers: _can_view()'s three distinct visibility rules (ADMIN always allowed
regardless of entity type; Message entities gated by kind -- direct messages only
visible to their two participants, channel messages gated by
core/messaging.py's can_access_channel; KnowledgePin entities gated by their own
active/visibility/roles/owner rule; every other entity type falling through to the
generic can_access_entity(role, entity_type)); explore_entity()'s real BFS
mechanics -- root-not-found and root-not-visible errors, depth clamping (None
defaults to 2, 0/negative clamps to 1, anything above MAX_DEPTH clamps to 3),
correct OUT/IN direction labeling depending on which side of the relationship the
current node is on, a node the caller can't view being dropped from the tree
entirely (not shown as a placeholder), the visited-set cycle guard preventing a
node from reappearing once already shown, the MAX_CHILDREN_PER_NODE=12 cap with an
accurate truncated_children count, real nested multi-level children, and the
shortest-path guarantee (a node with both a direct level-1 edge to the root AND a
longer path through another branch shows up at level 1, not buried deeper); and
graph_explore_api.py's thin pass-through.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT, MESSAGE, KNOWLEDGE_PIN
from core import graph_explore
from core import graph_explore_api
from core.knowledge_pins import VISIBILITY_ALL, VISIBILITY_ROLES
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


def _make_entity(entity_id, entity_type, **attrs):
    entity = Entity(id=entity_id, entity_type=entity_type, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _link(source_id, target_id, relationship_type, created_by=None, created_at=None):
    rel = Relationship(source_id=source_id, target_id=target_id, relationship_type=relationship_type, created_by=created_by, created_at=created_at)
    ledger.add_relationship(rel)
    return rel


class TestCanViewAdmin:

    def test_admin_can_always_view_any_entity_type_regardless_of_normal_gating(self):
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        assert graph_explore._can_view(contract, ADMIN, "EMP-1") is True

    def test_admin_can_always_view_a_direct_message_they_are_not_a_participant_in(self):
        message = _make_entity("MSG-1", MESSAGE, kind="direct", sender_id="EMP-A", recipient_id="EMP-B")
        assert graph_explore._can_view(message, ADMIN, "EMP-UNRELATED") is True

    def test_admin_can_always_view_an_inactive_knowledge_pin(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=False, visibility=VISIBILITY_ALL)
        assert graph_explore._can_view(pin, ADMIN, "EMP-1") is True


class TestCanViewMessages:

    def test_direct_message_visible_to_sender(self):
        message = _make_entity("MSG-1", MESSAGE, kind="direct", sender_id="EMP-A", recipient_id="EMP-B")
        assert graph_explore._can_view(message, SALES, "EMP-A") is True

    def test_direct_message_visible_to_recipient(self):
        message = _make_entity("MSG-1", MESSAGE, kind="direct", sender_id="EMP-A", recipient_id="EMP-B")
        assert graph_explore._can_view(message, SALES, "EMP-B") is True

    def test_direct_message_not_visible_to_an_unrelated_employee(self):
        message = _make_entity("MSG-1", MESSAGE, kind="direct", sender_id="EMP-A", recipient_id="EMP-B")
        assert graph_explore._can_view(message, SALES, "EMP-C") is False

    def test_channel_message_gated_by_can_access_channel(self):
        message = _make_entity("MSG-1", MESSAGE, kind="channel", channel_key="sales")
        # "sales" channel roles: OPERATIONS, SALES, MARKETING (per CHANNEL_DEFS).
        assert graph_explore._can_view(message, SALES, "EMP-1") is True
        assert graph_explore._can_view(message, SERVICE, "EMP-1") is False

    def test_channel_message_with_unknown_channel_key_denied_to_non_admin(self):
        message = _make_entity("MSG-1", MESSAGE, kind="channel", channel_key="not-a-real-channel")
        assert graph_explore._can_view(message, SALES, "EMP-1") is False


class TestCanViewKnowledgePins:

    def test_inactive_pin_denied_to_everyone_including_the_owner(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=False, visibility=VISIBILITY_ALL, owner_employee_id="EMP-1")
        assert graph_explore._can_view(pin, SALES, "EMP-1") is False

    def test_visibility_all_visible_to_any_role(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=True, visibility=VISIBILITY_ALL, owner_employee_id="EMP-9")
        assert graph_explore._can_view(pin, SERVICE, "EMP-1") is True

    def test_visibility_roles_visible_when_role_is_in_the_list(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=True, visibility=VISIBILITY_ROLES, roles=[SALES, MARKETING], owner_employee_id="EMP-9")
        assert graph_explore._can_view(pin, SALES, "EMP-1") is True

    def test_visibility_roles_denied_when_role_is_not_in_the_list(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=True, visibility=VISIBILITY_ROLES, roles=[SALES, MARKETING], owner_employee_id="EMP-9")
        assert graph_explore._can_view(pin, SERVICE, "EMP-1") is False

    def test_owner_can_always_view_their_own_pin_even_if_role_not_in_the_shared_list(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, active=True, visibility=VISIBILITY_ROLES, roles=[MARKETING], owner_employee_id="EMP-1")
        assert graph_explore._can_view(pin, SERVICE, "EMP-1") is True

    def test_active_defaults_true_when_absent(self):
        pin = _make_entity("PIN-1", KNOWLEDGE_PIN, visibility=VISIBILITY_ALL)
        assert graph_explore._can_view(pin, SALES, "EMP-1") is True


class TestCanViewGenericEntities:

    def test_broadly_visible_entity_type_allowed_for_every_role(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        for role in (OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            assert graph_explore._can_view(vehicle, role, "EMP-1") is True

    def test_restricted_entity_type_denied_to_roles_outside_its_access_list(self):
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        assert graph_explore._can_view(contract, FINANCE, "EMP-1") is True
        assert graph_explore._can_view(contract, OPERATIONS, "EMP-1") is True
        assert graph_explore._can_view(contract, SALES, "EMP-1") is False
        assert graph_explore._can_view(contract, MARKETING, "EMP-1") is False
        assert graph_explore._can_view(contract, SERVICE, "EMP-1") is False


class TestExploreEntityErrors:

    def test_entity_not_found(self):
        result = graph_explore.explore_entity("VEH-BOGUS", SALES, "EMP-1")
        assert result == {"error": "Entity not found"}

    def test_root_not_visible_to_caller_returns_forbidden(self):
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        result = graph_explore.explore_entity(contract.id, SALES, "EMP-1")
        assert result == {"error": "Forbidden: your role cannot access this entity"}

    def test_root_visible_to_caller_succeeds(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1")
        assert "error" not in result
        assert result["entity"]["id"] == vehicle.id


class TestExploreEntityDepthClamping:

    def test_none_depth_defaults_to_default_depth(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth=None)
        assert result["depth"] == graph_explore.DEFAULT_DEPTH

    def test_zero_depth_is_falsy_and_falls_back_to_default_depth(self):
        # `depth or DEFAULT_DEPTH` treats 0 as falsy, same as an omitted depth --
        # this is a real, if slightly surprising, consequence of the `or` idiom,
        # distinct from a genuinely negative depth (nonzero, so truthy).
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth=0)
        assert result["depth"] == graph_explore.DEFAULT_DEPTH

    def test_negative_depth_clamps_up_to_one(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth=-5)
        assert result["depth"] == 1

    def test_depth_above_max_clamps_down_to_max_depth(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth=99)
        assert result["depth"] == graph_explore.MAX_DEPTH

    def test_string_depth_within_range_is_coerced_to_int(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth="3")
        assert result["depth"] == 3


class TestExploreEntityTraversal:

    def test_single_out_edge_produces_one_child_with_correct_shape(self):
        customer = _make_entity("CUST-1", CUSTOMER, Name="Jane Doe")
        vehicle = _make_entity("VEH-1", VEHICLE, VIN="1FTFW1E50NKD00001")
        _link(customer.id, vehicle.id, "OWNS", created_by="EMP-1", created_at="2026-01-01T00:00:00")

        result = graph_explore.explore_entity(customer.id, SALES, "EMP-1", depth=1)

        assert len(result["children"]) == 1
        child = result["children"][0]
        assert child["direction"] == "OUT"
        assert child["relationship_type"] == "OWNS"
        assert child["created_by"] == "EMP-1"
        assert child["created_at"] == "2026-01-01T00:00:00"
        assert child["entity"]["id"] == vehicle.id
        assert child["entity"]["entity_type"] == VEHICLE
        assert child["entity"]["attributes"]["VIN"] == "1FTFW1E50NKD00001"

    def test_in_edge_labeled_correctly_from_the_roots_perspective(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        vehicle = _make_entity("VEH-1", VEHICLE)
        # Vehicle -> Customer this time, so from the CUSTOMER root's perspective the
        # relationship arrives (direction IN), not departs.
        _link(vehicle.id, customer.id, "OWNED_BY")

        result = graph_explore.explore_entity(customer.id, SALES, "EMP-1", depth=1)

        assert result["children"][0]["direction"] == "IN"
        assert result["children"][0]["entity"]["id"] == vehicle.id

    def test_unviewable_child_is_dropped_from_the_tree_entirely(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        _link(customer.id, contract.id, "FINANCED_BY")

        result = graph_explore.explore_entity(customer.id, SALES, "EMP-1", depth=1)
        assert result["children"] == []

        # The same root, viewed by a role that CAN see FINANCE_CONTRACT, shows it.
        result_finance = graph_explore.explore_entity(customer.id, FINANCE, "EMP-1", depth=1)
        assert len(result_finance["children"]) == 1

    def test_two_distinct_relationships_between_the_same_pair_both_show_up(self):
        # Real, intended multi-edge support: two separate relationship_type edges
        # connecting the same two nodes are NOT deduped into one child -- each real
        # relationship gets its own tree entry, since "already visited" is only
        # checked against nodes claimed in an EARLIER BFS round, not against other
        # candidates collected in the very same round.
        customer = _make_entity("CUST-1", CUSTOMER)
        vehicle = _make_entity("VEH-1", VEHICLE)
        _link(customer.id, vehicle.id, "OWNS")
        _link(vehicle.id, customer.id, "OWNED_BY")

        result = graph_explore.explore_entity(customer.id, SALES, "EMP-1", depth=1)

        assert len(result["children"]) == 2
        directions = {c["direction"] for c in result["children"]}
        assert directions == {"OUT", "IN"}
        assert all(c["entity"]["id"] == vehicle.id for c in result["children"])

    def test_visited_node_is_not_revisited_across_later_bfs_rounds(self):
        # B is reachable two ways: directly from root (level 1) and via A (level 2).
        # Since B is already claimed as root's own direct child by the time A is
        # explored, A's own edge to B is dropped rather than showing B a second time.
        root = _make_entity("CUST-1", CUSTOMER)
        node_a = _make_entity("VEH-A", VEHICLE)
        node_b = _make_entity("VEH-B", VEHICLE)
        _link(root.id, node_a.id, "OWNS")
        _link(root.id, node_b.id, "OWNS")
        _link(node_a.id, node_b.id, "OWNS")

        result = graph_explore.explore_entity(root.id, SALES, "EMP-1", depth=2)

        assert len(result["children"]) == 2
        node_a_tree = next(c for c in result["children"] if c["entity"]["id"] == node_a.id)
        assert node_a_tree["children"] == []

    def test_nested_children_at_depth_two(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        vehicle = _make_entity("VEH-1", VEHICLE)
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        _link(customer.id, vehicle.id, "OWNS")
        _link(vehicle.id, contract.id, "FINANCED_BY")

        result = graph_explore.explore_entity(customer.id, FINANCE, "EMP-1", depth=2)

        assert len(result["children"]) == 1
        vehicle_node = result["children"][0]
        assert len(vehicle_node["children"]) == 1
        assert vehicle_node["children"][0]["entity"]["id"] == contract.id

    def test_depth_one_does_not_include_second_level_children(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        vehicle = _make_entity("VEH-1", VEHICLE)
        contract = _make_entity("FIN-1", FINANCE_CONTRACT)
        _link(customer.id, vehicle.id, "OWNS")
        _link(vehicle.id, contract.id, "FINANCED_BY")

        result = graph_explore.explore_entity(customer.id, FINANCE, "EMP-1", depth=1)

        vehicle_node = result["children"][0]
        assert vehicle_node["children"] == []

    def test_max_children_per_node_cap_with_accurate_truncated_count(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        total = graph_explore.MAX_CHILDREN_PER_NODE + 3
        for i in range(total):
            vehicle = _make_entity(f"VEH-{i}", VEHICLE)
            _link(customer.id, vehicle.id, "OWNS")

        result = graph_explore.explore_entity(customer.id, SALES, "EMP-1", depth=1)

        assert len(result["children"]) == graph_explore.MAX_CHILDREN_PER_NODE
        assert result["truncated_children"] == 3

    def test_truncated_children_reported_on_a_non_root_node_too(self):
        customer = _make_entity("CUST-1", CUSTOMER)
        vehicle = _make_entity("VEH-1", VEHICLE)
        _link(customer.id, vehicle.id, "OWNS")

        total = graph_explore.MAX_CHILDREN_PER_NODE + 2
        for i in range(total):
            contract = _make_entity(f"FIN-{i}", FINANCE_CONTRACT)
            _link(vehicle.id, contract.id, "FINANCED_BY")

        result = graph_explore.explore_entity(customer.id, FINANCE, "EMP-1", depth=2)

        vehicle_node = result["children"][0]
        assert len(vehicle_node["children"]) == graph_explore.MAX_CHILDREN_PER_NODE
        assert vehicle_node["truncated_children"] == 2

    def test_shortest_path_wins_a_node_reachable_both_directly_and_via_a_longer_branch(self):
        root = _make_entity("CUST-1", CUSTOMER)
        branch_a = _make_entity("VEH-A", VEHICLE)
        shared = _make_entity("VEH-SHARED", VEHICLE)

        # root -> branch_a -> shared (a 2-hop path)
        _link(root.id, branch_a.id, "OWNS")
        _link(branch_a.id, shared.id, "OWNS")
        # root -> shared directly (a 1-hop path) -- this should win.
        _link(root.id, shared.id, "OWNS")

        result = graph_explore.explore_entity(root.id, SALES, "EMP-1", depth=2)

        top_level_ids = {c["entity"]["id"] for c in result["children"]}
        assert shared.id in top_level_ids

        branch_a_node = next(c for c in result["children"] if c["entity"]["id"] == branch_a.id)
        # shared was already claimed at level 1 -- branch_a's own attempt to reach it
        # at level 2 is skipped by the visited-set guard.
        assert branch_a_node["children"] == []

    def test_no_relationships_at_all_returns_empty_children(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore.explore_entity(vehicle.id, SALES, "EMP-1", depth=3)
        assert result["children"] == []
        assert result["truncated_children"] == 0

    def test_unrelated_relationships_elsewhere_in_the_graph_are_not_pulled_in(self):
        root = _make_entity("CUST-1", CUSTOMER)
        other_a = _make_entity("CUST-2", CUSTOMER)
        other_b = _make_entity("VEH-9", VEHICLE)
        _link(other_a.id, other_b.id, "OWNS")

        result = graph_explore.explore_entity(root.id, SALES, "EMP-1", depth=2)
        assert result["children"] == []


class TestGraphExploreApi:

    def test_pass_through_returns_the_same_shape_as_the_core_function(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore_api.explore_entity_api(SALES, "EMP-1", vehicle.id, depth=1)
        assert result["entity"]["id"] == vehicle.id
        assert result["depth"] == 1

    def test_pass_through_surfaces_errors_unmodified(self):
        result = graph_explore_api.explore_entity_api(SALES, "EMP-1", "VEH-BOGUS")
        assert result == {"error": "Entity not found"}

    def test_default_depth_omitted_uses_default_depth(self):
        vehicle = _make_entity("VEH-1", VEHICLE)
        result = graph_explore_api.explore_entity_api(SALES, "EMP-1", vehicle.id)
        assert result["depth"] == graph_explore.DEFAULT_DEPTH
