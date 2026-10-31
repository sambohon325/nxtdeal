"""
Tests for core/smart_audiences.py -- the Smart Audiences engine added in session 113
(Marketing Growth Platform kickoff, 2026-07-17). This is the first committed regression
coverage for that module, added per BUILD_QUEUE.md's standing "convert the loose
test_*.py scripts to a real backend/tests/ pytest suite as each module gets touched"
rule, and the natural next step in the Marketing-engine test arc (email_templates ->
marketing_lists -> dealership_events -> this).

The module is load-bearing marketing infrastructure: a SmartAudience is a saved,
reusable segment DEFINITION (a no-code AND-chain of field/operator/value conditions, or
one of eight named PRESET_AUDIENCES) that is re-evaluated LIVE against the current graph
on every read -- never a frozen membership snapshot (that's what
core/marketing_lists.py's MarketingList is; a SmartAudience can be frozen into one via
"Save as List"). It carried real, untested logic worth locking:

  * the generic `_apply_operator` comparison kernel (=, !=, >, >=, <, <=, contains) with
    its numeric-vs-string coercion rule and None/uncastable fail-closed behaviour;
  * `_customer_matches_conditions`' AND-only chain with vehicle/finance conditions
    matching if ANY owned vehicle/deal satisfies them, and unknown fields failing closed;
  * all eight preset audiences -- the heuristic ones (truck-model keyword match, the
    Condition+DateSold warranty-window math, the ContractDate+TermMonths lease-maturity
    math, the CreditScore<660 subprime band with its tolerant string parsing, the
    in_house-financing BHPH resolver) computed here, and the three that delegate to real
    engines elsewhere (`campaigns.build_audience` retention/finance_renewal,
    `workflow_tab_data.marketing_database_mining` positive-equity), which are
    monkeypatched so the test exercises smart_audiences' OWN wiring, not theirs;
  * `get_equity_candidate_for_customer`'s single-customer candidate resolution;
  * `evaluate_preset`/`preview_preset`/`preview_conditions`/`list_presets` shaping incl.
    the 10-member sample cap and unknown-preset error passthrough;
  * the `_serialize_member` per-entity-type shape (Customer name/email/phone with
    blank-name->id fallback; non-Customer -> id-only);
  * the CRUD lifecycle -- `create_audience` (name-required + unknown-preset validation,
    defaults, ledger persistence), `delete_audience` (missing/wrong-type guard),
    `list_audiences` created_at reverse sort, and `evaluate_audience`'s live
    preset-vs-conditions dispatch; and
  * the `smart_audiences_api` ACL layer's view-vs-mutate role gating.

Everything seeds directly into the ledger and stubs save_graph, so it's deterministic,
seed-independent, and never touches the real graph.json -- same precautions
tests/test_marketing_lists.py / tests/test_dealership_events.py document. It imports only
the ledger chain (not the FUSE-truncated *_menu/api.app modules), so it runs green in the
sandbox. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import timedelta

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import (
    CUSTOMER,
    VEHICLE,
    FINANCE_CONTRACT,
    DEAL,
    SMART_AUDIENCE,
)

from core import smart_audiences
from core import smart_audiences_api


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + id counters before/after every test. ledger.reset() clears
    entities AND relationships but does NOT reset id_generator counters, so ids would
    otherwise leak across tests (same rule tests/test_marketing_lists.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """smart_audiences.py does `from core.storage import save_graph`, so patch the
    imported reference in its namespace -- otherwise every create/delete would clobber
    the real graph.json (the conftest temp-dir isolation is belt-and-suspenders on top
    of this)."""

    monkeypatch.setattr(smart_audiences, "save_graph", lambda *a, **k: None)


def _add_customer(cid=None, first="Jane", last="Doe", credit=None, email=None, phone=None, custkey=None):
    cid = cid or id_generator.generate("CUST")
    attrs = {"FirstName": first, "LastName": last}
    if credit is not None:
        attrs["CreditScore"] = credit
    if email is not None:
        attrs["Email"] = email
    if phone is not None:
        attrs["Phone"] = phone
    if custkey is not None:
        attrs["CustomerID"] = custkey
    c = Entity(id=cid, entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(c)
    return c


def _add_vehicle(vid=None, **attrs):
    vid = vid or id_generator.generate("VEH")
    v = Entity(id=vid, entity_type=VEHICLE, attributes=dict(attrs))
    ledger.add_entity(v)
    return v


def _owns(customer, vehicle):
    ledger.add_relationship(Relationship(source_id=customer.id, target_id=vehicle.id, relationship_type="OWNS"))


_fc_seq = [0]


def _add_contract(customer, cid=None, **attrs):
    if cid is None:
        _fc_seq[0] += 1
        cid = f"FC-{_fc_seq[0]:05}"
    fc = Entity(id=cid, entity_type=FINANCE_CONTRACT, attributes=dict(attrs))
    ledger.add_entity(fc)
    ledger.add_relationship(Relationship(source_id=customer.id, target_id=fc.id, relationship_type="FINANCED_BY"))
    return fc


def _add_deal(customer_id, did=None, financing_type=None):
    did = did or id_generator.generate("DEAL")
    attrs = {"customer_id": customer_id}
    if financing_type is not None:
        attrs["financing_type"] = financing_type
    d = Entity(id=did, entity_type=DEAL, attributes=attrs)
    ledger.add_entity(d)
    return d


def _isodate(d):
    return d.isoformat()


# ==========================================================================
# _apply_operator -- the comparison kernel
# ==========================================================================


def test_apply_operator_none_actual_always_false():
    for op in smart_audiences.OPERATORS:
        assert smart_audiences._apply_operator(None, op, "x") is False


def test_apply_operator_numeric_comparisons():
    assert smart_audiences._apply_operator("75000", ">", 50000) is True
    assert smart_audiences._apply_operator("40000", ">", 50000) is False
    assert smart_audiences._apply_operator(50000, ">=", "50000") is True
    assert smart_audiences._apply_operator("49999", "<", 50000) is True
    assert smart_audiences._apply_operator(50000, "<=", 50000) is True
    assert smart_audiences._apply_operator("2020", "=", 2020) is True
    assert smart_audiences._apply_operator("2020", "!=", 2021) is True


def test_apply_operator_string_equality_case_insensitive():
    assert smart_audiences._apply_operator("Ford", "=", "ford") is True
    assert smart_audiences._apply_operator("Ford", "!=", "toyota") is True
    # A non-numeric expected string routes through the lowercased string branch even
    # for order operators.
    assert smart_audiences._apply_operator("Ford", ">", "toyota") is False


def test_apply_operator_contains():
    assert smart_audiences._apply_operator("Ford F-150 XLT", "contains", "f-150") is True
    assert smart_audiences._apply_operator("Silverado", "contains", "tacoma") is False


def test_apply_operator_uncastable_numeric_is_false():
    # expected is numeric-looking so it takes the float() branch; "abc" can't cast.
    assert smart_audiences._apply_operator("abc", ">", "100") is False


def test_apply_operator_unknown_operator_falls_through_false():
    assert smart_audiences._apply_operator("5", "~=", "5") is False


# ==========================================================================
# evaluate_conditions / _customer_matches_conditions
# ==========================================================================


def test_evaluate_conditions_empty_matches_everyone():
    a = _add_customer(first="A")
    b = _add_customer(first="B")
    result = evaluate = smart_audiences.evaluate_conditions([])
    ids = {c.id for c in result}
    assert ids == {a.id, b.id}


def test_evaluate_conditions_none_matches_everyone():
    a = _add_customer(first="A")
    assert [c.id for c in smart_audiences.evaluate_conditions(None)] == [a.id]


def test_evaluate_conditions_credit_score():
    hi = _add_customer(first="Hi", credit="720")
    lo = _add_customer(first="Lo", credit="600")
    conds = [{"field": "customer.credit_score", "operator": ">=", "value": 660}]
    ids = {c.id for c in smart_audiences.evaluate_conditions(conds)}
    assert ids == {hi.id}


def test_evaluate_conditions_vehicle_any_match():
    c = _add_customer()
    _owns(c, _add_vehicle(Make="Ford", Model="Focus"))
    _owns(c, _add_vehicle(Make="Ford", Model="F-150"))
    conds = [{"field": "vehicle.model", "operator": "contains", "value": "F-150"}]
    # A customer with multiple vehicles qualifies if ONE of them matches.
    assert [x.id for x in smart_audiences.evaluate_conditions(conds)] == [c.id]


def test_evaluate_conditions_vehicle_no_match_excludes():
    c = _add_customer()
    _owns(c, _add_vehicle(Make="Toyota", Model="Camry"))
    conds = [{"field": "vehicle.make", "operator": "=", "value": "Ford"}]
    assert smart_audiences.evaluate_conditions(conds) == []


def test_evaluate_conditions_and_chain():
    match = _add_customer(first="Match", credit="700")
    _owns(match, _add_vehicle(Make="Ford", Model="F-250", Mileage="80000"))
    # Same vehicle but low mileage -> fails the second clause.
    partial = _add_customer(first="Partial", credit="700")
    _owns(partial, _add_vehicle(Make="Ford", Model="F-250", Mileage="10000"))
    conds = [
        {"field": "vehicle.make", "operator": "=", "value": "Ford"},
        {"field": "vehicle.mileage", "operator": ">", "value": 75000},
    ]
    ids = {c.id for c in smart_audiences.evaluate_conditions(conds)}
    assert ids == {match.id}


def test_evaluate_conditions_finance_type_via_deal():
    inhouse = _add_customer(first="In")
    _add_deal(inhouse.id, financing_type="in_house")
    bank = _add_customer(first="Bank")
    _add_deal(bank.id, financing_type="bank")
    conds = [{"field": "finance.financing_type", "operator": "=", "value": "in_house"}]
    assert [c.id for c in smart_audiences.evaluate_conditions(conds)] == [inhouse.id]


def test_evaluate_conditions_unknown_field_fails_closed():
    _add_customer(first="Anyone")
    conds = [{"field": "customer.favorite_color", "operator": "=", "value": "blue"}]
    # Fail closed -- an unknown field must NOT silently match everyone.
    assert smart_audiences.evaluate_conditions(conds) == []


# ==========================================================================
# preset: truck owners (heuristic keyword)
# ==========================================================================


def test_truck_owners_keyword_match():
    truck = _add_customer(first="Truck")
    _owns(truck, _add_vehicle(Make="Ford", Model="F-150 XLT"))
    car = _add_customer(first="Car")
    _owns(car, _add_vehicle(Make="Honda", Model="Civic"))
    ids = {c.id for c in smart_audiences._truck_owners()}
    assert ids == {truck.id}


def test_truck_owners_dedupes_multi_truck_customer():
    c = _add_customer()
    _owns(c, _add_vehicle(Model="Silverado 1500"))
    _owns(c, _add_vehicle(Model="Tacoma"))
    # break after the first matching vehicle -> customer appears once, not twice.
    assert [x.id for x in smart_audiences._truck_owners()] == [c.id]


# ==========================================================================
# preset: warranty expiring (heuristic Condition + DateSold window)
# ==========================================================================


def test_warranty_expiring_in_window():
    c = _add_customer()
    sold = smart_audiences._today() - timedelta(days=1050)  # 1005..1095 window
    v = _add_vehicle(Condition="New", DateSold=_isodate(sold))
    _owns(c, v)
    assert [x.id for x in smart_audiences._warranty_expiring()] == [c.id]


def test_warranty_expiring_excludes_used():
    c = _add_customer()
    sold = smart_audiences._today() - timedelta(days=1050)
    _owns(c, _add_vehicle(Condition="Used", DateSold=_isodate(sold)))
    assert smart_audiences._warranty_expiring() == []


def test_warranty_expiring_excludes_too_recent_sale():
    c = _add_customer()
    sold = smart_audiences._today() - timedelta(days=30)  # days_to_expiration ~1065 > 90
    _owns(c, _add_vehicle(Condition="Certified Pre-Owned", DateSold=_isodate(sold)))
    assert smart_audiences._warranty_expiring() == []


def test_warranty_expiring_skips_missing_datesold():
    c = _add_customer()
    _owns(c, _add_vehicle(Condition="New"))
    assert smart_audiences._warranty_expiring() == []


# ==========================================================================
# preset: lease ending (ContractDate + TermMonths maturity math)
# ==========================================================================


def test_lease_ending_within_window():
    c = _add_customer()
    # term 36mo -> 1080 days; contract 1020 days ago -> maturity in 60 days -> qualifies.
    contract_date = smart_audiences._today() - timedelta(days=1020)
    _add_contract(c, ContractDate=_isodate(contract_date), TermMonths=36)
    assert [x.id for x in smart_audiences._lease_ending_in_days(120)] == [c.id]


def test_lease_ending_excludes_already_matured():
    c = _add_customer()
    contract_date = smart_audiences._today() - timedelta(days=2000)
    _add_contract(c, ContractDate=_isodate(contract_date), TermMonths=36)
    assert smart_audiences._lease_ending_in_days(120) == []


def test_lease_ending_excludes_beyond_horizon():
    c = _add_customer()
    # maturity ~1080 days out, far beyond a 120-day horizon.
    contract_date = smart_audiences._today()
    _add_contract(c, ContractDate=_isodate(contract_date), TermMonths=36)
    assert smart_audiences._lease_ending_in_days(120) == []


def test_lease_ending_skips_missing_or_bad_term():
    c = _add_customer()
    contract_date = smart_audiences._today() - timedelta(days=1020)
    _add_contract(c, ContractDate=_isodate(contract_date), TermMonths="not-a-number")
    assert smart_audiences._lease_ending_in_days(120) == []


# ==========================================================================
# preset: subprime (CreditScore < 660, tolerant string parse)
# ==========================================================================


def test_subprime_customers_threshold():
    sub = _add_customer(first="Sub", credit="620")
    prime = _add_customer(first="Prime", credit="700")
    boundary = _add_customer(first="Edge", credit="660")  # not < 660
    ids = {c.id for c in smart_audiences._subprime_customers()}
    assert ids == {sub.id}
    assert prime.id not in ids and boundary.id not in ids


def test_subprime_skips_unparseable_score():
    _add_customer(first="Bad", credit="N/A")
    _add_customer(first="None")  # no CreditScore attribute at all
    assert smart_audiences._subprime_customers() == []


# ==========================================================================
# preset: BHPH (Deal.financing_type == in_house resolved to customer)
# ==========================================================================


def test_bhph_customers_resolves_in_house_deal():
    c = _add_customer(first="Bhph")
    _add_deal(c.id, financing_type="in_house")
    other = _add_customer(first="Bank")
    _add_deal(other.id, financing_type="bank")
    assert [x.id for x in smart_audiences._bhph_customers()] == [c.id]


def test_bhph_skips_deal_with_no_resolvable_customer():
    _add_deal("CUST-DOES-NOT-EXIST", financing_type="in_house")
    assert smart_audiences._bhph_customers() == []


# ==========================================================================
# presets that delegate to real engines elsewhere (monkeypatched)
# ==========================================================================


def test_no_service_delegates_to_campaign_retention(monkeypatch):
    calls = {}

    def fake_build(kind, params):
        calls["args"] = (kind, params)
        return ["SENTINEL"]

    monkeypatch.setattr(smart_audiences, "_campaign_build_audience", fake_build)
    out = smart_audiences._no_service_in_months(8)
    assert out == ["SENTINEL"]
    assert calls["args"] == ("retention", {"months_since_service": 8})


def test_potential_refinance_delegates_to_finance_renewal(monkeypatch):
    calls = {}

    def fake_build(kind, params):
        calls["args"] = (kind, params)
        return ["SENTINEL"]

    monkeypatch.setattr(smart_audiences, "_campaign_build_audience", fake_build)
    out = smart_audiences._potential_refinance(3)
    assert out == ["SENTINEL"]
    assert calls["args"] == ("finance_renewal", {"months_to_maturity": 3})


def test_positive_equity_resolves_mining_candidates(monkeypatch):
    c = _add_customer(first="Equity")
    monkeypatch.setattr(
        smart_audiences,
        "marketing_database_mining",
        lambda role: {"candidates": [{"customer_id": c.id}, {"customer_id": "MISSING"}]},
    )
    assert [x.id for x in smart_audiences._positive_equity()] == [c.id]


def test_positive_equity_resolves_via_raw_key_fallback(monkeypatch):
    # A raw import key (CustomerID attr) that isn't a graph id still resolves through
    # the module's defensive lookup-by-raw-key fallback.
    c = _add_customer(first="Raw", custkey="C4077")
    monkeypatch.setattr(
        smart_audiences,
        "marketing_database_mining",
        lambda role: {"candidates": [{"customer_id": "C4077"}]},
    )
    assert [x.id for x in smart_audiences._positive_equity()] == [c.id]


def test_get_equity_candidate_for_customer_hit_and_miss(monkeypatch):
    c = _add_customer(first="Cand")
    cand = {"customer_id": c.id, "pct_term_elapsed": 0.7}
    monkeypatch.setattr(
        smart_audiences,
        "marketing_database_mining",
        lambda role: {"candidates": [cand]},
    )
    assert smart_audiences.get_equity_candidate_for_customer(c.id) == cand
    assert smart_audiences.get_equity_candidate_for_customer("CUST-OTHER") is None


# ==========================================================================
# list_presets / evaluate_preset / preview_preset / preview_conditions
# ==========================================================================


def test_list_presets_shape():
    presets = smart_audiences.list_presets()
    keys = {p["key"] for p in presets}
    assert keys == {
        "truck_owners", "no_service_in_months", "warranty_expiring", "lease_ending",
        "positive_equity", "subprime_customers", "bhph_customers", "potential_refinance",
    }
    for p in presets:
        assert set(p.keys()) == {"key", "name", "basis", "params"}
    # "fn" is never leaked to callers.
    assert all("fn" not in p for p in presets)


def test_evaluate_preset_unknown_key_errors():
    out = smart_audiences.evaluate_preset("does_not_exist")
    assert "error" in out


def test_evaluate_preset_returns_member_result():
    sub = _add_customer(first="Sub", credit="600")
    out = smart_audiences.evaluate_preset("subprime_customers")
    assert out["preset"] == "subprime_customers"
    assert out["basis"] == "real"
    assert out["count"] == 1
    assert out["members"][0].id == sub.id


def test_preview_preset_error_passthrough():
    assert "error" in smart_audiences.preview_preset("nope")


def test_preview_preset_caps_sample_at_ten():
    for i in range(15):
        _add_customer(first=f"S{i}", credit="600")
    out = smart_audiences.preview_preset("subprime_customers")
    assert out["count"] == 15
    assert len(out["sample"]) == 10
    assert all(set(m.keys()) == {"id", "name", "email", "phone"} for m in out["sample"])


def test_preview_conditions_shape():
    _add_customer(first="A", credit="600")
    _add_customer(first="B", credit="700")
    out = smart_audiences.preview_conditions(
        [{"field": "customer.credit_score", "operator": "<", "value": 660}]
    )
    assert out["count"] == 1
    assert len(out["sample"]) == 1


# ==========================================================================
# _serialize_member
# ==========================================================================


def test_serialize_member_customer():
    c = _add_customer(first="Jane", last="Doe", email="j@x.com", phone="555")
    out = smart_audiences._serialize_member(c)
    assert out == {"id": c.id, "name": "Jane Doe", "email": "j@x.com", "phone": "555"}


def test_serialize_member_customer_blank_name_falls_back_to_id():
    c = _add_customer(cid="CUST-77", first="", last="")
    out = smart_audiences._serialize_member(c)
    assert out["name"] == "CUST-77"


def test_serialize_member_non_customer_id_only():
    v = _add_vehicle(vid="VEH-9", Model="F-150")
    assert smart_audiences._serialize_member(v) == {"id": "VEH-9", "name": "VEH-9"}


# ==========================================================================
# CRUD: create / delete / list / evaluate_audience
# ==========================================================================


def test_create_audience_requires_name():
    assert "error" in smart_audiences.create_audience("", "EMP-1")
    assert "error" in smart_audiences.create_audience("   ", "EMP-1")


def test_create_audience_rejects_unknown_preset():
    out = smart_audiences.create_audience("X", "EMP-1", preset_key="not_a_preset")
    assert "error" in out


def test_create_audience_defaults_and_persists():
    ent = smart_audiences.create_audience("My Segment", "EMP-1", description="hi")
    assert isinstance(ent, Entity)
    assert ent.entity_type == SMART_AUDIENCE
    assert ent.id.startswith("AUD-")
    assert ent.attributes["name"] == "My Segment"
    assert ent.attributes["description"] == "hi"
    assert ent.attributes["conditions"] == []
    assert ent.attributes["preset_params"] == {}
    assert ent.attributes["created_by"] == "EMP-1"
    assert ent.attributes["created_at"] and ent.attributes["updated_at"]
    # actually landed in the ledger
    assert ledger.get_entity(ent.id) is ent


def test_create_audience_strips_name():
    ent = smart_audiences.create_audience("  Padded  ", "EMP-1")
    assert ent.attributes["name"] == "Padded"


def test_delete_audience_missing_errors():
    assert "error" in smart_audiences.delete_audience("AUD-404")


def test_delete_audience_wrong_type_errors():
    c = _add_customer()
    assert "error" in smart_audiences.delete_audience(c.id)


def test_delete_audience_removes_from_ledger():
    ent = smart_audiences.create_audience("Temp", "EMP-1")
    out = smart_audiences.delete_audience(ent.id)
    assert out == {"deleted": ent.id}
    assert ledger.get_entity(ent.id) is None


def test_list_audiences_reverse_created_at_sort():
    a = smart_audiences.create_audience("First", "EMP-1")
    a.attributes["created_at"] = "2026-01-01T00:00:00+00:00"
    b = smart_audiences.create_audience("Second", "EMP-1")
    b.attributes["created_at"] = "2026-06-01T00:00:00+00:00"
    ordered = [x.id for x in smart_audiences.list_audiences()]
    assert ordered == [b.id, a.id]


def test_evaluate_audience_missing_errors():
    assert "error" in smart_audiences.evaluate_audience("AUD-404")


def test_evaluate_audience_conditions_based():
    sub = _add_customer(first="Sub", credit="600")
    _add_customer(first="Prime", credit="720")
    ent = smart_audiences.create_audience(
        "Subprime custom", "EMP-1",
        conditions=[{"field": "customer.credit_score", "operator": "<", "value": 660}],
    )
    out = smart_audiences.evaluate_audience(ent.id)
    assert out["basis"] == "custom_conditions"
    assert out["count"] == 1
    assert out["member_ids"] == [sub.id]
    assert out["members"][0]["id"] == sub.id


def test_evaluate_audience_preset_based():
    sub = _add_customer(first="Sub", credit="600")
    ent = smart_audiences.create_audience(
        "Subprime preset", "EMP-1", preset_key="subprime_customers",
    )
    out = smart_audiences.evaluate_audience(ent.id)
    assert out["basis"] == "real"
    assert out["member_ids"] == [sub.id]


def test_evaluate_audience_live_reflects_new_data():
    ent = smart_audiences.create_audience(
        "Subprime preset", "EMP-1", preset_key="subprime_customers",
    )
    assert smart_audiences.evaluate_audience(ent.id)["count"] == 0
    _add_customer(first="Late", credit="600")
    # membership is re-computed on every read, never frozen at save time.
    assert smart_audiences.evaluate_audience(ent.id)["count"] == 1


# ==========================================================================
# smart_audiences_api -- ACL layer role gating
# ==========================================================================


def test_api_view_gating():
    # SALES (a view role) allowed; FINANCE (not a view role) forbidden.
    assert "error" not in smart_audiences_api.list_presets_api("SALES")
    assert "error" in smart_audiences_api.list_presets_api("FINANCE")


def test_api_field_catalog_shape():
    out = smart_audiences_api.get_field_catalog_api("MARKETING")
    assert out["fields"] == smart_audiences.FIELD_CATALOG
    assert out["operators"] == smart_audiences.OPERATORS


def test_api_mutate_gating():
    # MARKETING can create; SALES (view-only) cannot.
    ok = smart_audiences_api.create_audience_api("MARKETING", "Seg", "EMP-1")
    assert isinstance(ok, Entity)
    denied = smart_audiences_api.create_audience_api("SALES", "Seg", "EMP-1")
    assert "error" in denied
    # SALES also can't delete.
    assert "error" in smart_audiences_api.delete_audience_api("SALES", ok.id)


def test_api_list_audiences_shape():
    ent = smart_audiences_api.create_audience_api("ADMIN", "Seg", "EMP-1")
    out = smart_audiences_api.list_audiences_api("OPERATIONS")
    assert out["audiences"][0]["id"] == ent.id
    assert set(out["audiences"][0].keys()) == {
        "id", "name", "description", "preset_key", "conditions", "created_by", "created_at",
    }
