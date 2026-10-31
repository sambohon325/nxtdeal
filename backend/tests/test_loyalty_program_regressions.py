import pytest
from core import loyalty_program as lp
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import APPOINTMENT
from tests.test_loyalty_program import isolated_program, program, purchase


def test_saving_draft_does_not_pause_active_program(program):
    config, _, _ = program
    lp.save_document("program", config | {"status":"draft", "earning_enabled":False}, "marketing")
    assert lp.workspace()["program"]["status"] == "draft"
    assert lp.workspace()["active_program"]["status"] == "active"
    assert lp.process_purchase(purchase(), "integration")["points"] == 3000


def test_cancelled_appointment_releases_on_next_read(program):
    _, reward, _ = program
    lp.adjust("C1", 3000, "Opening", "admin", "opening")
    h = lp.reserve("C1", reward["id"], "APPT-CANCEL", "STORE-1", "service", "hold")
    old = ledger.get_entity("APPT-CANCEL")
    ledger.add_entity(Entity(id="APPT-CANCEL", entity_type=APPOINTMENT,
                             attributes={"customer_id":"C1", "status":"cancelled"}))
    try:
        assert lp.get_member("C1")["available"] == 3000
        with pytest.raises(lp.LoyaltyError, match="no longer active"):
            lp.resolve_hold("C1", h["reservation_id"], "confirm", "service", "confirm", "RO", "Applied")
    finally:
        if old:
            ledger.add_entity(old)
        else:
            ledger.entities.pop("APPT-CANCEL", None)


def test_new_rate_without_date_does_not_rewrite_past(program):
    _, _, rule = program
    lp.save_document("rule", rule | {"points":10}, "marketing")
    assert lp.process_purchase(purchase(), "integration")["points"] == 3000


def test_overlapping_base_rules_enter_exception_queue_without_points(program):
    lp.save_document("rule", dict(name="Overlapping",status="active",trigger="service",calculation="fixed",points=99),"marketing")
    assert lp.process_purchase(purchase(),"integration")["status"] == "failed"
    assert lp.get_member("C1")["posted"] == 0


def test_backup_includes_a_consistent_ledger(program, tmp_path):
    import sqlite3
    lp.process_purchase(purchase(), "integration")
    destination = tmp_path / "snapshot.sqlite3"
    assert lp.backup_database(destination) == str(destination)
    lp.adjust("C1", 100, "After backup", "admin", "adjust-after")
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT SUM(points) FROM entries WHERE customer_id='C1'").fetchone()[0] == 3000
    assert lp.get_member("C1")["posted"] == 3100


def test_graph_only_restore_is_blocked_when_program_exists(program):
    from core.data_backup import restore_backup
    result = restore_backup("ANY", "admin")
    assert "paired loyalty database" in result["error"]
