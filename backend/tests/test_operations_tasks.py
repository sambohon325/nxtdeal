"""
Tests for core/operations_tasks.py -- the "Universal Operations Work Queue" added in
session 106 (Operations spec, third slice after Vehicles and Overview + Action Center,
2026-07-16). This is the first committed regression coverage for that module, added per
BUILD_QUEUE.md's standing "convert the loose test_*.py scripts to a real backend/tests/
pytest suite as each module gets touched" rule (the same item sessions 46/48/49/71-80/108/
the 2026-07-22..25 runs each advanced by one module).

The module is load-bearing Operations infrastructure and had ZERO coverage. An
OperationsTask is a real, first-class graph entity (core/entity_types.py's OPERATIONS_TASK)
with its own open -> in_progress -> closed lifecycle, distinct from the additive-attribute
convention used for Vehicle Lifecycle -- a task isn't a property of one entity, it's its
own trackable unit of work, optionally *about* an entity via a plain `linked_entity_id`
attribute (not a foreign key). SLA tracking is computed LIVE off created_at at read time
(hours_open, is_overdue vs a per-priority SLA-hours table) -- the same "compute live, no
scheduler" convention core/vehicle_holds.py uses for expires_at -- so it's worth pinning
that the enrichment never mutates the stored entity and that is_overdue only fires on an
open task past its window. Several sibling modules (document_workflows, inventory_aging,
operations_scheduling, workflow_automation) create tasks through this engine, so its
validation + persistence contract is load-bearing well beyond its own dashboard.

Worth locking here:

  * the static catalogs/tables (OWNER_BUCKETS, TASK_TYPES, STATUSES, PRIORITIES, the
    SLA_HOURS threshold table);
  * the live SLA helpers -- `_parse` (None / bad string / naive->utc / aware passthrough),
    `_hours_open` (None created_at, uses closed_at when present else now), `_enrich`
    (adds hours_open/sla_hours/is_overdue WITHOUT mutating the stored entity, is_overdue
    only when open + past sla);
  * `serialize_task` (dict passthrough vs Entity -> {id, **attributes});
  * `create_task` validation (bad task_type/priority/owner_bucket -> error, no save fired),
    draft defaults (status open, detail ""-coerced, derived flag = bool(source_entity_id)),
    and the save-fired-once / `_skip_save` batching contract;
  * `get_task` hit(enriched)/miss/wrong-type;
  * `update_task` not-found + bad status/priority/owner_bucket guards, the started_at
    stamp-once rule, the closed_at/closed_by stamp on close, the reopen-clears-close-stamp
    rule, and the assigned_to update;
  * `close_task` not-found / already-closed / success (resolution_notes None -> "");
  * `escalate_task` not-found / closed / success (priority -> urgent + appended note);
  * `list_tasks` every filter (status/owner_bucket/assigned_to/priority/overdue_only) and
    the priority-then-created_at sort;
  * `get_stats` rollup shape (total/open/closed/overdue/by_owner_bucket);
  * the three bulk actions (assign/close/reprioritize) delegating per-id;
  * `_existing_source_ids` non-closed-only dedup key and `sync_derived_tasks` turning the
    three real read-only signals (wholesale disposition / lot audit / open compliance
    alerts) into deduped, trackable tasks -- with the two signal source modules
    (core.workflow_tab_data, core.compliance_api) stubbed via sys.modules so this test
    exercises operations_tasks' OWN sync wiring without pulling the openai/menu chain.

Everything seeds directly into the ledger and stubs save_graph, so it's deterministic,
seed-independent, and never touches the real graph.json (the conftest temp-dir isolation
is belt-and-suspenders on top of this). operations_tasks.py imports only the ledger chain
(dealeros/entities/entity_types/storage/storage_paths), so it collects and runs GREEN in
the sandbox -- immune to the FUSE-truncation trap that blocks the heavier *_menu/api.app
chain. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import types
from datetime import datetime, timedelta, timezone

import pytest

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import OPERATIONS_TASK, VEHICLE

from core import operations_tasks as ot


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + id counters before/after every test. ledger.reset() clears
    entities AND relationships but does NOT reset id_generator counters, so ids (incl.
    OTASK) would otherwise leak across tests (same rule tests/test_advertising.py and
    tests/test_smart_audiences.py document)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_save(monkeypatch):
    """operations_tasks.py does `from core.storage import save_graph` -- patch the
    imported reference in its namespace so creating/mutating a task never clobbers the
    real graph.json (the conftest temp-dir isolation is additional belt-and-suspenders
    on top of this). Also count fires so save-once / _skip_save can be asserted."""

    ot._save_calls = 0

    def _count_save(*a, **k):
        ot._save_calls += 1

    monkeypatch.setattr(ot, "save_graph", _count_save)


def _backdate(task_id, hours_ago):
    """Rewrite a task's stored created_at to N hours in the past so the live SLA clock
    (hours_open / is_overdue) can be exercised deterministically."""

    raw = ledger.get_entity(task_id)
    raw.attributes["created_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    ).isoformat()
    return raw


def _new(task_type="custom", detail="do a thing", created_by="EMP-1", **kw):
    return ot.create_task(task_type, detail, created_by, **kw)


# --------------------------------------------------------------------------
# static catalogs / tables
# --------------------------------------------------------------------------


def test_owner_buckets_are_the_five_spec_buckets_plus_unassigned():
    assert ot.OWNER_BUCKETS == [
        "Inventory Manager", "Title Clerk", "Service Manager",
        "Lot Manager", "Accounting", "Unassigned",
    ]


def test_task_types_include_the_derived_and_custom_kinds():
    for t in ("transfer_to_wholesale", "confirm_lot_audit",
              "review_compliance_exception", "document_request", "custom"):
        assert t in ot.TASK_TYPES


def test_statuses_and_priorities_catalogs():
    assert ot.STATUSES == ["open", "in_progress", "closed"]
    assert ot.PRIORITIES == ["low", "normal", "high", "urgent"]


def test_sla_hours_table_orders_urgent_shortest_low_longest():
    assert ot.SLA_HOURS == {"urgent": 4, "high": 24, "normal": 72, "low": 168}
    assert ot.SLA_HOURS["urgent"] < ot.SLA_HOURS["high"] < ot.SLA_HOURS["normal"] < ot.SLA_HOURS["low"]


# --------------------------------------------------------------------------
# live SLA helpers -- _parse / _hours_open / _enrich
# --------------------------------------------------------------------------


def test_parse_none_and_empty_return_none():
    assert ot._parse(None) is None
    assert ot._parse("") is None


def test_parse_bad_string_returns_none():
    assert ot._parse("not-a-timestamp") is None


def test_parse_naive_string_is_assumed_utc():
    dt = ot._parse("2026-01-01T00:00:00")
    assert dt.tzinfo == timezone.utc


def test_parse_aware_string_keeps_offset():
    dt = ot._parse("2026-01-01T00:00:00+00:00")
    assert dt is not None
    assert dt.utcoffset() == timedelta(0)


def test_hours_open_none_when_no_created_at():
    t = Entity(id="OTASK-X", entity_type=OPERATIONS_TASK, attributes={})
    assert ot._hours_open(t) is None


def test_hours_open_counts_to_now_when_open():
    t = Entity(id="OTASK-X", entity_type=OPERATIONS_TASK, attributes={
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
    })
    assert ot._hours_open(t) == pytest.approx(5.0, abs=0.1)


def test_hours_open_freezes_at_closed_at_when_closed():
    created = datetime.now(timezone.utc) - timedelta(hours=10)
    closed = created + timedelta(hours=3)
    t = Entity(id="OTASK-X", entity_type=OPERATIONS_TASK, attributes={
        "created_at": created.isoformat(),
        "closed_at": closed.isoformat(),
    })
    # 3 hours between created and closed, NOT the full 10 to now.
    assert ot._hours_open(t) == pytest.approx(3.0, abs=0.05)


def test_enrich_adds_sla_fields_without_mutating_stored_entity():
    t = _new(priority="high")
    tid = t.id
    raw = ledger.get_entity(tid)
    enriched = ot._enrich(raw)
    assert "hours_open" in enriched.attributes
    assert enriched.attributes["sla_hours"] == 24  # high
    # the stored entity is untouched by enrichment
    assert "hours_open" not in raw.attributes
    assert "is_overdue" not in raw.attributes


def test_enrich_is_overdue_true_only_when_open_and_past_sla():
    t = _new(priority="urgent")  # 4h sla
    _backdate(t.id, hours_ago=5)
    assert ot.get_task(t.id).attributes["is_overdue"] is True


def test_enrich_not_overdue_within_sla_window():
    t = _new(priority="normal")  # 72h sla
    _backdate(t.id, hours_ago=1)
    assert ot.get_task(t.id).attributes["is_overdue"] is False


def test_enrich_closed_task_never_overdue_even_if_old():
    t = _new(priority="urgent")
    _backdate(t.id, hours_ago=100)
    ot.close_task(t.id, closed_by="EMP-2")
    assert ot.get_task(t.id).attributes["is_overdue"] is False


def test_enrich_unknown_priority_falls_back_to_normal_sla():
    t = _new()
    raw = ledger.get_entity(t.id)
    raw.attributes["priority"] = "bogus"
    assert ot._enrich(raw).attributes["sla_hours"] == ot.SLA_HOURS["normal"]


# --------------------------------------------------------------------------
# serialize_task
# --------------------------------------------------------------------------


def test_serialize_task_passes_dicts_through_untouched():
    d = {"id": "OTASK-9", "status": "open"}
    assert ot.serialize_task(d) is d


def test_serialize_task_flattens_entity_to_id_plus_attributes():
    t = _new(detail="flatten me")
    flat = ot.serialize_task(ledger.get_entity(t.id))
    assert flat["id"] == t.id
    assert flat["detail"] == "flatten me"
    assert "attributes" not in flat  # not nested one level deeper


# --------------------------------------------------------------------------
# create_task
# --------------------------------------------------------------------------


def test_create_task_rejects_unknown_task_type_without_saving():
    res = _new(task_type="not_a_type")
    assert "error" in res
    assert ot._save_calls == 0


def test_create_task_rejects_unknown_priority():
    res = _new(priority="critical")
    assert "error" in res
    assert ot._save_calls == 0


def test_create_task_rejects_unknown_owner_bucket():
    res = _new(owner_bucket="Janitor")
    assert "error" in res
    assert ot._save_calls == 0


def test_create_task_defaults_and_persists():
    t = _new()
    assert isinstance(t, Entity)
    assert t.entity_type == OPERATIONS_TASK
    a = t.attributes
    assert a["status"] == "open"
    assert a["priority"] == "normal"
    assert a["owner_bucket"] == "Unassigned"
    assert a["started_at"] is None
    assert a["closed_at"] is None
    assert a["resolution_notes"] == ""
    assert a["derived"] is False
    assert ot._save_calls == 1
    # actually in the ledger
    assert ledger.get_entity(t.id) is not None


def test_create_task_coerces_none_detail_to_empty_string():
    t = ot.create_task("custom", None, "EMP-1")
    assert t.attributes["detail"] == ""


def test_create_task_with_source_entity_id_marks_derived():
    t = _new(source_entity_id="VEH-7")
    assert t.attributes["derived"] is True
    assert t.attributes["source_entity_id"] == "VEH-7"


def test_create_task_skip_save_suppresses_persistence():
    ot.create_task("custom", "batched", "EMP-1", _skip_save=True)
    assert ot._save_calls == 0


def test_create_task_ids_use_otask_prefix():
    t = _new()
    assert t.id.startswith("OTASK-")


# --------------------------------------------------------------------------
# get_task
# --------------------------------------------------------------------------


def test_get_task_hit_returns_enriched():
    t = _new()
    got = ot.get_task(t.id)
    assert got.id == t.id
    assert "is_overdue" in got.attributes


def test_get_task_missing_returns_none():
    assert ot.get_task("OTASK-99999") is None


def test_get_task_wrong_entity_type_returns_none():
    ledger.add_entity(Entity(id="VEH-1", entity_type=VEHICLE, attributes={}))
    assert ot.get_task("VEH-1") is None


# --------------------------------------------------------------------------
# update_task
# --------------------------------------------------------------------------


def test_update_task_missing_returns_error():
    assert "error" in ot.update_task("OTASK-99999", "EMP-2", status="closed")


def test_update_task_rejects_bad_status():
    t = _new()
    assert "error" in ot.update_task(t.id, "EMP-2", status="frozen")


def test_update_task_rejects_bad_priority():
    t = _new()
    assert "error" in ot.update_task(t.id, "EMP-2", priority="nuclear")


def test_update_task_rejects_bad_owner_bucket():
    t = _new()
    assert "error" in ot.update_task(t.id, "EMP-2", owner_bucket="Nobody")


def test_update_task_in_progress_stamps_started_at_once():
    t = _new()
    r1 = ot.update_task(t.id, "EMP-2", status="in_progress")
    first = r1.attributes["started_at"]
    assert first is not None
    # set to open then back to in_progress -- started_at must not be overwritten
    ot.update_task(t.id, "EMP-2", status="open")
    r2 = ot.update_task(t.id, "EMP-2", status="in_progress")
    assert r2.attributes["started_at"] == first


def test_update_task_close_stamps_closed_fields():
    t = _new()
    r = ot.update_task(t.id, "EMP-2", status="closed")
    assert r.attributes["status"] == "closed"
    assert r.attributes["closed_at"] is not None
    assert r.attributes["closed_by"] == "EMP-2"


def test_update_task_reopen_clears_close_stamp():
    t = _new()
    ot.update_task(t.id, "EMP-2", status="closed")
    r = ot.update_task(t.id, "EMP-3", status="open")
    assert r.attributes["closed_at"] is None
    assert r.attributes["closed_by"] is None


def test_update_task_updates_priority_owner_and_assignee():
    t = _new()
    r = ot.update_task(t.id, "EMP-2", priority="high", owner_bucket="Title Clerk", assigned_to="EMP-9")
    assert r.attributes["priority"] == "high"
    assert r.attributes["owner_bucket"] == "Title Clerk"
    assert r.attributes["assigned_to"] == "EMP-9"


# --------------------------------------------------------------------------
# close_task
# --------------------------------------------------------------------------


def test_close_task_missing_returns_error():
    assert "error" in ot.close_task("OTASK-99999", "EMP-2")


def test_close_task_success_sets_all_close_fields():
    t = _new()
    r = ot.close_task(t.id, "EMP-2", resolution_notes="done and dusted")
    assert r.attributes["status"] == "closed"
    assert r.attributes["closed_by"] == "EMP-2"
    assert r.attributes["resolution_notes"] == "done and dusted"


def test_close_task_already_closed_returns_error():
    t = _new()
    ot.close_task(t.id, "EMP-2")
    assert "error" in ot.close_task(t.id, "EMP-3")


def test_close_task_coerces_none_notes_to_empty_string():
    t = _new()
    r = ot.close_task(t.id, "EMP-2", resolution_notes=None)
    assert r.attributes["resolution_notes"] == ""


# --------------------------------------------------------------------------
# escalate_task
# --------------------------------------------------------------------------


def test_escalate_task_missing_returns_error():
    assert "error" in ot.escalate_task("OTASK-99999", "EMP-2")


def test_escalate_task_bumps_priority_to_urgent_and_appends_note():
    t = _new(priority="low")
    r = ot.escalate_task(t.id, "EMP-2", notes="customer is livid")
    assert r.attributes["priority"] == "urgent"
    assert "escalated by EMP-2" in r.attributes["resolution_notes"]
    assert "customer is livid" in r.attributes["resolution_notes"]


def test_escalate_closed_task_returns_error():
    t = _new()
    ot.close_task(t.id, "EMP-2")
    assert "error" in ot.escalate_task(t.id, "EMP-3")


# --------------------------------------------------------------------------
# list_tasks -- filters + sort
# --------------------------------------------------------------------------


def test_list_tasks_status_filter():
    a = _new()
    b = _new()
    ot.close_task(b.id, "EMP-2")
    open_ids = [t.id for t in ot.list_tasks(status="open")]
    assert a.id in open_ids and b.id not in open_ids


def test_list_tasks_owner_bucket_filter():
    a = _new(owner_bucket="Title Clerk")
    _new(owner_bucket="Accounting")
    ids = [t.id for t in ot.list_tasks(owner_bucket="Title Clerk")]
    assert ids == [a.id]


def test_list_tasks_assigned_to_filter():
    a = _new(assigned_to="EMP-9")
    _new(assigned_to="EMP-8")
    ids = [t.id for t in ot.list_tasks(assigned_to="EMP-9")]
    assert ids == [a.id]


def test_list_tasks_priority_filter():
    a = _new(priority="high")
    _new(priority="low")
    ids = [t.id for t in ot.list_tasks(priority="high")]
    assert ids == [a.id]


def test_list_tasks_overdue_only():
    old = _new(priority="urgent")
    _backdate(old.id, hours_ago=10)
    fresh = _new(priority="urgent")  # created now, not overdue
    ids = [t.id for t in ot.list_tasks(overdue_only=True)]
    assert old.id in ids and fresh.id not in ids


def test_list_tasks_sorts_by_priority_then_created_at():
    low = _new(priority="low")
    urgent = _new(priority="urgent")
    normal = _new(priority="normal")
    order = [t.attributes["priority"] for t in ot.list_tasks()]
    assert order.index("urgent") < order.index("normal") < order.index("low")


# --------------------------------------------------------------------------
# get_stats
# --------------------------------------------------------------------------


def test_get_stats_rollup_shape_and_counts():
    a = _new(owner_bucket="Title Clerk")
    b = _new(owner_bucket="Title Clerk")
    c = _new(owner_bucket="Accounting")
    ot.close_task(c.id, "EMP-2")
    overdue = _new(priority="urgent", owner_bucket="Accounting")
    _backdate(overdue.id, hours_ago=10)

    stats = ot.get_stats()
    assert stats["total"] == 4
    assert stats["closed"] == 1
    assert stats["open"] == 3
    assert stats["overdue"] == 1
    assert stats["by_owner_bucket"]["Title Clerk"] == 2
    # closed task's bucket is excluded from the open by_owner rollup
    assert stats["by_owner_bucket"].get("Accounting") == 1


# --------------------------------------------------------------------------
# bulk actions
# --------------------------------------------------------------------------


def test_bulk_assign_updates_every_id():
    a = _new()
    b = _new()
    res = ot.bulk_assign([a.id, b.id], "EMP-9", "Lot Manager", "EMP-1")
    assert len(res) == 2
    for r in res:
        assert r.attributes["assigned_to"] == "EMP-9"
        assert r.attributes["owner_bucket"] == "Lot Manager"


def test_bulk_close_closes_every_id():
    a = _new()
    b = _new()
    res = ot.bulk_close([a.id, b.id], "EMP-1", resolution_notes="batch done")
    assert all(r.attributes["status"] == "closed" for r in res)
    assert all(r.attributes["resolution_notes"] == "batch done" for r in res)


def test_bulk_reprioritize_sets_priority_on_every_id():
    a = _new(priority="low")
    b = _new(priority="normal")
    res = ot.bulk_reprioritize([a.id, b.id], "high", "EMP-1")
    assert all(r.attributes["priority"] == "high" for r in res)


def test_bulk_close_reports_error_for_missing_id():
    a = _new()
    res = ot.bulk_close([a.id, "OTASK-99999"], "EMP-1")
    assert res[0].attributes["status"] == "closed"
    assert "error" in res[1]


# --------------------------------------------------------------------------
# _existing_source_ids  +  sync_derived_tasks
# --------------------------------------------------------------------------


def test_existing_source_ids_only_counts_non_closed_of_that_type():
    open_t = _new(task_type="transfer_to_wholesale", source_entity_id="VEH-1")
    closed_t = _new(task_type="transfer_to_wholesale", source_entity_id="VEH-2")
    ot.close_task(closed_t.id, "EMP-2")
    _new(task_type="confirm_lot_audit", source_entity_id="VEH-3")  # different type

    ids = ot._existing_source_ids("transfer_to_wholesale")
    assert ids == {"VEH-1"}


def _stub_signal_modules(monkeypatch, wholesale, lot_audit, alerts):
    """Inject fake core.workflow_tab_data + core.compliance_api modules so
    sync_derived_tasks' function-local imports resolve to our controlled returns
    without pulling the real (openai/menu) import chain."""

    wtd = types.ModuleType("core.workflow_tab_data")
    wtd.inventory_wholesale_disposition = lambda role: wholesale
    wtd.inventory_lot_audit = lambda role: lot_audit
    monkeypatch.setitem(sys.modules, "core.workflow_tab_data", wtd)

    capi = types.ModuleType("core.compliance_api")
    capi.list_alerts_api = lambda role, status=None: alerts
    monkeypatch.setitem(sys.modules, "core.compliance_api", capi)


def test_sync_derived_tasks_creates_one_per_signal(monkeypatch):
    _stub_signal_modules(
        monkeypatch,
        wholesale={"candidates": [
            {"vehicle_id": "VEH-1", "year": 2020, "make": "Ford", "model": "F150", "margin_pct": "5%"},
        ]},
        lot_audit={"discrepancies": [{"vehicle_id": "VEH-2", "vin": "1FT-XYZ"}]},
        alerts={"alerts": [{"id": "ALERT-1", "law": "Reg Z", "severity": "high"}]},
    )
    created = ot.sync_derived_tasks("OPERATIONS")
    assert created == {
        "transfer_to_wholesale": 1,
        "confirm_lot_audit": 1,
        "review_compliance_exception": 1,
    }
    types_created = sorted(t.attributes["task_type"] for t in ot.list_tasks())
    assert types_created == ["confirm_lot_audit", "review_compliance_exception", "transfer_to_wholesale"]


def test_sync_derived_tasks_is_idempotent_for_still_open_signals(monkeypatch):
    signals = dict(
        wholesale={"candidates": [
            {"vehicle_id": "VEH-1", "year": 2020, "make": "Ford", "model": "F150", "margin_pct": "5%"},
        ]},
        lot_audit={"discrepancies": []},
        alerts={"alerts": []},
    )
    _stub_signal_modules(monkeypatch, **signals)
    ot.sync_derived_tasks("OPERATIONS")
    # re-run against the same still-open signal -- no duplicate ticket
    second = ot.sync_derived_tasks("OPERATIONS")
    assert second["transfer_to_wholesale"] == 0
    assert len([t for t in ot.list_tasks() if t.attributes["task_type"] == "transfer_to_wholesale"]) == 1


def test_sync_derived_tasks_high_severity_alert_is_urgent(monkeypatch):
    _stub_signal_modules(
        monkeypatch,
        wholesale={"candidates": []},
        lot_audit={"discrepancies": []},
        alerts={"alerts": [
            {"id": "ALERT-1", "law": "OFAC", "severity": "high"},
            {"id": "ALERT-2", "law": "CAN-SPAM", "severity": "medium"},
        ]},
    )
    ot.sync_derived_tasks("OPERATIONS")
    by_source = {t.attributes["source_entity_id"]: t.attributes["priority"]
                 for t in ot.list_tasks() if t.attributes["task_type"] == "review_compliance_exception"}
    assert by_source["ALERT-1"] == "urgent"
    assert by_source["ALERT-2"] == "high"


def test_sync_derived_tasks_skips_candidates_missing_vehicle_id(monkeypatch):
    _stub_signal_modules(
        monkeypatch,
        wholesale={"candidates": [{"year": 2020, "make": "Ford", "model": "F150", "margin_pct": "5%"}]},
        lot_audit={"discrepancies": []},
        alerts={"alerts": []},
    )
    created = ot.sync_derived_tasks("OPERATIONS")
    assert created["transfer_to_wholesale"] == 0


def test_sync_derived_tasks_tolerates_non_dict_signal_returns(monkeypatch):
    # workflow_tab_data helpers can return an error string/None on a bad role --
    # the isinstance(..., dict) guards must keep sync from raising.
    _stub_signal_modules(
        monkeypatch,
        wholesale="permission denied",
        lot_audit=None,
        alerts={"nope": True},
    )
    created = ot.sync_derived_tasks("OPERATIONS")
    assert created == {
        "transfer_to_wholesale": 0,
        "confirm_lot_audit": 0,
        "review_compliance_exception": 0,
    }
