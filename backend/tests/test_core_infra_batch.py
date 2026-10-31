"""
Test coverage for a handful of foundational, low-level `core/` modules that
predate (and, in most cases, sit underneath) the graph-unification work --
see the CLAUDE.md missing_test_coverage / CAF-00123 effort.

Covers: core/id_generator.py (IDGenerator), core/ledger.py (the DealerLedger
class definition itself, as opposed to the `core.dealeros.ledger` singleton
instance every other test file already exercises indirectly), core/registry.py
(EntityRegistry), core/repository.py (the GraphRepository singleton), and
core/workflows.py (the real, still-active LEAD_WORKFLOW state machine --
confirmed alive via real imports in core/lead_pipeline_api.py,
core/lead_workflows.py, and core/marketing_menu.py, distinct from the
confirmed-orphaned core/workflow_repository.py/workflow_instances.py/
workflow_storage.py/assignment_storage.py family documented in CLAUDE.md's
Known Gaps section).

NOT covered here, and deliberately so: core/pipeline.py's get_pipeline_summary()
is dead code -- a full-repo grep found zero real importers anywhere in core/,
api/, or hub/, confirming it was superseded by core/pipeline_state.py's own
pipeline-summary logic during the 2026-07-13 graph-unification pass, the exact
same fate task #180 already documented for core/schema.py, core/validation.py,
and core/indexes.py (also zero real importers, also superseded). Writing tests
for genuinely dead code doesn't reduce any real risk, so it's skipped here too.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# id_generator.py
# ---------------------------------------------------------------------------

from core.id_generator import IDGenerator


class TestIDGenerator:

    def test_fresh_instance_starts_every_known_prefix_at_zero(self):
        gen = IDGenerator()
        assert gen.counters["VEH"] == 0
        assert gen.counters["CUST"] == 0
        assert gen.counters["DEAL"] == 0

    def test_generate_increments_and_formats_with_zero_padding(self):
        gen = IDGenerator()
        assert gen.generate("VEH") == "VEH-00001"
        assert gen.generate("VEH") == "VEH-00002"
        assert gen.generate("VEH") == "VEH-00003"

    def test_generate_tracks_each_prefix_independently(self):
        gen = IDGenerator()
        assert gen.generate("CUST") == "CUST-00001"
        assert gen.generate("LEAD") == "LEAD-00001"
        assert gen.generate("CUST") == "CUST-00002"
        assert gen.counters["CUST"] == 2
        assert gen.counters["LEAD"] == 1

    def test_generate_unknown_prefix_raises_key_error(self):
        gen = IDGenerator()
        with pytest.raises(KeyError):
            gen.generate("TOTALLY_UNKNOWN_PREFIX")

    def test_two_instances_do_not_share_state(self):
        gen_a = IDGenerator()
        gen_b = IDGenerator()
        gen_a.generate("EMP")
        gen_a.generate("EMP")
        assert gen_a.counters["EMP"] == 2
        assert gen_b.counters["EMP"] == 0

    def test_generate_pads_to_five_digits_and_beyond(self):
        gen = IDGenerator()
        gen.counters["SITE"] = 99998
        assert gen.generate("SITE") == "SITE-99999"
        assert gen.generate("SITE") == "SITE-100000"


# ---------------------------------------------------------------------------
# ledger.py (the DealerLedger class definition, tested directly rather than
# only via the core.dealeros.ledger singleton every other test file uses)
# ---------------------------------------------------------------------------

from core.ledger import DealerLedger


class TestDealerLedgerClass:

    def test_fresh_ledger_starts_empty(self):
        l = DealerLedger()
        assert l.entities == {}
        assert l.relationships == []

    def test_add_entity_and_get_entity_round_trip(self):
        l = DealerLedger()
        e = Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Ford"})
        l.add_entity(e)
        assert l.get_entity("VEH-00001") is e

    def test_get_entity_missing_returns_none(self):
        l = DealerLedger()
        assert l.get_entity("VEH-99999") is None

    def test_get_all_returns_the_live_entities_dict(self):
        l = DealerLedger()
        e1 = Entity(id="VEH-00001", entity_type="Vehicle", attributes={})
        e2 = Entity(id="VEH-00002", entity_type="Vehicle", attributes={})
        l.add_entity(e1)
        l.add_entity(e2)
        result = l.get_all()
        assert set(result.keys()) == {"VEH-00001", "VEH-00002"}

    def test_add_entity_overwrites_same_id(self):
        l = DealerLedger()
        e1 = Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Ford"})
        e2 = Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Chevrolet"})
        l.add_entity(e1)
        l.add_entity(e2)
        assert l.get_entity("VEH-00001").attributes["Make"] == "Chevrolet"
        assert len(l.get_all()) == 1

    def test_add_relationship_and_get_relationships(self):
        l = DealerLedger()
        r = Relationship(source_id="CUST-00001", target_id="VEH-00001", relationship_type="OWNS")
        l.add_relationship(r)
        assert l.get_relationships() == [r]

    def test_get_entity_relationships_filters_by_source_or_target(self):
        l = DealerLedger()
        r1 = Relationship(source_id="CUST-00001", target_id="VEH-00001", relationship_type="OWNS")
        r2 = Relationship(source_id="CUST-00002", target_id="VEH-00002", relationship_type="OWNS")
        r3 = Relationship(source_id="LEAD-00001", target_id="CUST-00001", relationship_type="BECAME")
        l.add_relationship(r1)
        l.add_relationship(r2)
        l.add_relationship(r3)
        result = l.get_entity_relationships("CUST-00001")
        assert r1 in result
        assert r3 in result
        assert r2 not in result

    def test_get_entity_relationships_empty_when_no_matches(self):
        l = DealerLedger()
        l.add_relationship(Relationship(source_id="CUST-00001", target_id="VEH-00001", relationship_type="OWNS"))
        assert l.get_entity_relationships("CUST-99999") == []

    def test_reset_clears_entities_and_relationships_in_place(self):
        l = DealerLedger()
        l.add_entity(Entity(id="VEH-00001", entity_type="Vehicle", attributes={}))
        l.add_relationship(Relationship(source_id="A", target_id="B", relationship_type="X"))
        l.reset()
        assert l.entities == {}
        assert l.relationships == []

    def test_reset_preserves_object_identity_for_holders_of_a_reference(self):
        # The whole reason reset() clears in place instead of reassigning self --
        # a caller holding a direct reference to this same object (like
        # core.dealeros's module-level `ledger` singleton) must see the cleared
        # state too, not a stale pre-reset snapshot.
        l = DealerLedger()
        held_reference = l
        l.add_entity(Entity(id="VEH-00001", entity_type="Vehicle", attributes={}))
        l.reset()
        assert held_reference.entities == {}

    def test_real_singleton_ledger_from_dealeros_is_a_dealer_ledger_instance(self):
        # Confirms core.dealeros's real `ledger` singleton (used by every other
        # test file in this suite) is genuinely built from this class.
        assert isinstance(ledger, DealerLedger)


# ---------------------------------------------------------------------------
# registry.py
# ---------------------------------------------------------------------------

from core.registry import EntityRegistry


class TestEntityRegistry:

    def test_fresh_registry_starts_with_empty_lookup_dicts(self):
        r = EntityRegistry()
        assert r.vehicle_vins == {}
        assert r.customer_ids == {}
        assert r.lead_ids == {}
        assert r.finance_ids == {}
        assert r.lenders == {}
        assert r.employee_ids == {}
        assert r.part_numbers == {}

    def test_vehicle_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_vehicle("1FTFW1ET1EFA00001", "VEH-00001")
        assert r.find_vehicle("1FTFW1ET1EFA00001") == "VEH-00001"

    def test_vehicle_find_missing_returns_none(self):
        r = EntityRegistry()
        assert r.find_vehicle("NOPE") is None

    def test_customer_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_customer("C1001", "CUST-00001")
        assert r.find_customer("C1001") == "CUST-00001"

    def test_lead_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_lead("L2001", "LEAD-00001")
        assert r.find_lead("L2001") == "LEAD-00001"

    def test_finance_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_finance("F3001", "FIN-00001")
        assert r.find_finance("F3001") == "FIN-00001"

    def test_lender_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_lender("Chrysler Capital", "LENDER-00001")
        assert r.find_lender("Chrysler Capital") == "LENDER-00001"

    def test_employee_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_employee("E4001", "EMP-00001")
        assert r.find_employee("E4001") == "EMP-00001"

    def test_part_register_and_find_round_trip(self):
        r = EntityRegistry()
        r.register_part("PN-9001", "PART-00001")
        assert r.find_part("PN-9001") == "PART-00001"

    def test_registering_same_key_twice_overwrites(self):
        r = EntityRegistry()
        r.register_vehicle("SAME-VIN", "VEH-00001")
        r.register_vehicle("SAME-VIN", "VEH-00002")
        assert r.find_vehicle("SAME-VIN") == "VEH-00002"

    def test_lookup_categories_are_independent_of_each_other(self):
        # A key registered under one category shouldn't leak into another --
        # e.g. registering a VIN doesn't make it findable as a customer id.
        r = EntityRegistry()
        r.register_vehicle("SHARED-KEY", "VEH-00001")
        assert r.find_customer("SHARED-KEY") is None
        assert r.find_lead("SHARED-KEY") is None


# ---------------------------------------------------------------------------
# repository.py (the real GraphRepository singleton, backed by the real
# core.dealeros.ledger singleton -- same fresh_ledger fixture as every other
# test file, since this module is a thin passthrough over that shared state)
# ---------------------------------------------------------------------------

from core.repository import repository, GraphRepository


class TestGraphRepository:

    def test_repository_is_a_module_level_singleton(self):
        assert isinstance(repository, GraphRepository)

    def test_get_entity_delegates_to_the_real_ledger(self):
        e = Entity(id="VEH-00001", entity_type="Vehicle", attributes={"Make": "Ford"})
        ledger.add_entity(e)
        assert repository.get_entity("VEH-00001") is e

    def test_get_entity_missing_returns_none(self):
        assert repository.get_entity("VEH-99999") is None

    def test_get_entities_returns_a_list_of_every_real_entity(self):
        ledger.add_entity(Entity(id="VEH-00001", entity_type="Vehicle", attributes={}))
        ledger.add_entity(Entity(id="CUST-00001", entity_type="Customer", attributes={}))
        result = repository.get_entities()
        assert isinstance(result, list)
        ids = {e.id for e in result}
        assert ids == {"VEH-00001", "CUST-00001"}

    def test_get_entities_empty_when_ledger_is_empty(self):
        assert repository.get_entities() == []

    def test_get_relationships_delegates_to_the_real_ledger(self):
        r = Relationship(source_id="CUST-00001", target_id="VEH-00001", relationship_type="OWNS")
        ledger.add_relationship(r)
        assert repository.get_relationships() == [r]

    def test_get_relationships_empty_when_ledger_is_empty(self):
        assert repository.get_relationships() == []

    def test_a_second_graph_repository_instance_shares_the_same_underlying_ledger(self):
        # GraphRepository has no per-instance state of its own -- every instance
        # reads from the same module-level core.dealeros.ledger singleton.
        second_repo = GraphRepository()
        ledger.add_entity(Entity(id="VEH-00001", entity_type="Vehicle", attributes={}))
        assert second_repo.get_entity("VEH-00001") is repository.get_entity("VEH-00001")


# ---------------------------------------------------------------------------
# workflows.py (LEAD_WORKFLOW -- the real, currently-active state machine,
# confirmed alive via core/lead_pipeline_api.py, core/lead_workflows.py, and
# core/marketing_menu.py; pure functions, no ledger dependency at all)
# ---------------------------------------------------------------------------

from core.workflows import (
    LEAD_WORKFLOW,
    get_next_states,
    can_transition,
    transition_state,
    transition_with_history,
)


class TestWorkflows:

    def test_lead_workflow_covers_every_expected_state(self):
        assert set(LEAD_WORKFLOW.keys()) == {
            "NEW", "CONTACTED", "APPOINTMENT_SET", "VISITED",
            "PROPOSAL", "NEGOTIATION", "SOLD", "LOST",
        }

    def test_sold_and_lost_are_terminal_states(self):
        assert LEAD_WORKFLOW["SOLD"] == []
        assert LEAD_WORKFLOW["LOST"] == []

    def test_get_next_states_returns_the_real_outgoing_edges(self):
        assert get_next_states("NEW") == ["CONTACTED"]
        assert get_next_states("NEGOTIATION") == ["SOLD", "LOST"]

    def test_get_next_states_unknown_state_returns_empty_list(self):
        assert get_next_states("NOT_A_REAL_STATE") == []

    def test_get_next_states_terminal_state_returns_empty_list(self):
        assert get_next_states("SOLD") == []
        assert get_next_states("LOST") == []

    def test_can_transition_true_for_a_real_valid_edge(self):
        assert can_transition("NEW", "CONTACTED") is True
        assert can_transition("NEGOTIATION", "SOLD") is True
        assert can_transition("NEGOTIATION", "LOST") is True

    def test_can_transition_false_for_an_invalid_edge(self):
        assert can_transition("NEW", "SOLD") is False
        assert can_transition("SOLD", "LOST") is False

    def test_can_transition_false_from_a_terminal_state(self):
        assert can_transition("SOLD", "NEGOTIATION") is False
        assert can_transition("LOST", "CONTACTED") is False

    def test_transition_state_returns_the_next_state_on_a_valid_edge(self):
        assert transition_state("NEW", "CONTACTED") == "CONTACTED"

    def test_transition_state_raises_on_an_invalid_edge(self):
        with pytest.raises(ValueError):
            transition_state("NEW", "SOLD")

    def test_transition_state_raises_from_a_terminal_state(self):
        with pytest.raises(ValueError):
            transition_state("SOLD", "NEGOTIATION")

    def test_transition_with_history_appends_a_real_entry_with_state_and_timestamp(self):
        history = [{"state": "NEW", "timestamp": "2026-01-01T00:00:00"}]
        result = transition_with_history(history, "CONTACTED")
        assert result is history
        assert len(history) == 2
        assert history[-1]["state"] == "CONTACTED"
        assert "timestamp" in history[-1]

    def test_transition_with_history_reads_current_state_from_the_last_entry(self):
        history = [
            {"state": "NEW", "timestamp": "2026-01-01T00:00:00"},
            {"state": "CONTACTED", "timestamp": "2026-01-02T00:00:00"},
        ]
        transition_with_history(history, "APPOINTMENT_SET")
        assert history[-1]["state"] == "APPOINTMENT_SET"

    def test_transition_with_history_raises_on_an_invalid_edge_and_does_not_mutate(self):
        history = [{"state": "SOLD", "timestamp": "2026-01-01T00:00:00"}]
        with pytest.raises(ValueError):
            transition_with_history(history, "NEGOTIATION")
        # history should be untouched -- the append only happens after the
        # can_transition check passes.
        assert len(history) == 1
        assert history[-1]["state"] == "SOLD"
