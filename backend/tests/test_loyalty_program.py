from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import loyalty_program as lp


@pytest.fixture(autouse=True)
def isolated_program(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(tmp_path))


@pytest.fixture
def program():
    config = lp.save_document("program", lp.DEFAULT_PROGRAM | {
        "status": "active", "enrollment_enabled": True,
        "earning_enabled": True, "redemption_enabled": True,
    }, "admin")
    lp.enroll("C1", "Customer One", "admin", "enroll-1", "1")
    lp.enroll("C2", "Customer Two", "admin", "enroll-2", "1")
    reward = lp.save_document("reward", dict(name="$25 service reward", status="active",
        point_cost=2500, department="Service", locations=["STORE-1"]), "marketing")
    rule = lp.save_document("rule", dict(name="Service points", status="active",
        trigger="service", calculation="per_dollar", points=1), "marketing")
    return config, reward, rule


def purchase(**changes):
    return dict(source_system="dms", source_id="RO-1", customer_id="C1", kind="service",
                eligible_cents=300000, location="STORE-1", status="finalized",
                occurred_at="2026-10-01T12:00:00+00:00") | changes


def test_complete_purchase_reserve_redeem_and_earn(program):
    _, reward, _ = program
    lp.process_purchase(purchase(), "integration")
    h = lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "hold")
    m = lp.get_member("C1")
    assert (m["posted"], m["reserved"], m["available"]) == (3000, 2500, 500)
    lp.resolve_hold("C1", h["reservation_id"], "confirm", "service", "confirm", "RO-2", "Applied $25 on finalized invoice")
    lp.process_purchase(purchase(source_id="RO-2", eligible_cents=17500), "integration")
    m = lp.get_member("C1")
    assert (m["posted"], m["reserved"], m["available"]) == (675, 0, 675)


def test_duplicate_purchase_and_changed_payload(program):
    first = lp.process_purchase(purchase(), "integration")
    assert lp.process_purchase(purchase(), "integration") == first
    assert lp.get_member("C1")["available"] == 3000
    with pytest.raises(lp.LoyaltyError, match="different data"):
        lp.process_purchase(purchase(eligible_cents=900000), "integration")


def test_concurrent_reservations_cannot_overspend(program):
    _, reward, _ = program
    lp.adjust("C1", 3000, "Opening points", "admin", "opening")
    def reserve(i):
        try:
            return lp.reserve("C1", reward["id"], f"APPT-{i}", "STORE-1", "service", f"hold-{i}")
        except lp.LoyaltyError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(8)))
    assert sum(r is not None for r in results) == 1
    assert lp.get_member("C1")["available"] == 500


def test_same_request_concurrently_returns_one_hold(program):
    _, reward, _ = program
    lp.adjust("C1", 3000, "Opening points", "admin", "opening")
    def reserve(_):
        return lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "same")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(4)))
    assert len({r["reservation_id"] for r in results}) == 1


def test_request_key_cannot_change_operation(program):
    lp.adjust("C1", 100, "Support", "admin", "same-key")
    with pytest.raises(lp.LoyaltyError, match="different action"):
        lp.adjust("C1", 999, "Support", "admin", "same-key")
    assert lp.get_member("C1")["posted"] == 100


def test_cancel_and_expired_holds_release_points(program):
    _, reward, _ = program
    lp.adjust("C1", 5000, "Opening points", "admin", "opening")
    h = lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "hold")
    lp.resolve_hold("C1", h["reservation_id"], "release", "service", "cancel")
    lp.resolve_hold("C1", h["reservation_id"], "release", "service", "cancel")
    assert lp.get_member("C1")["available"] == 5000
    h = lp.reserve("C1", reward["id"], "APPT-2", "STORE-1", "service", "hold-2")
    with lp.transaction() as db:
        db.execute("UPDATE holds SET expires_at='2000-01-01' WHERE id=?", (h["reservation_id"],))
    assert lp.get_member("C1")["available"] == 5000
    with pytest.raises(lp.LoyaltyError, match="no longer active"):
        lp.resolve_hold("C1", h["reservation_id"], "confirm", "service", "late", "RO-2", "Applied")


def test_cannot_access_another_members_reservation(program):
    _, reward, _ = program
    lp.adjust("C1", 5000, "Opening", "admin", "opening")
    h = lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "hold")
    with pytest.raises(lp.LoyaltyError, match="not found"):
        lp.resolve_hold("C2", h["reservation_id"], "release", "service", "steal")


def test_duplicate_invoice_cannot_redeem_twice(program):
    _, reward, _ = program
    lp.adjust("C1", 10000, "Opening", "admin", "opening")
    first = lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "hold")
    second = lp.reserve("C1", reward["id"], "APPT-2", "STORE-1", "service", "hold2")
    lp.resolve_hold("C1", first["reservation_id"], "confirm", "service", "confirm", "RO-2", "Applied")
    with pytest.raises(lp.LoyaltyError, match="already has"):
        lp.resolve_hold("C1", second["reservation_id"], "confirm", "service", "confirm2", "RO-2", "Applied")


def test_partial_refunds_cannot_reverse_more_than_original(program):
    lp.process_purchase(purchase(), "integration")
    original = lp.get_member("C1")["entries"][0]["id"]
    lp.reverse("C1", original, 1000, "Partial refund", "admin", "refund-1")
    lp.reverse("C1", original, 2000, "Remaining refund", "admin", "refund-2")
    assert lp.get_member("C1")["posted"] == 0
    with pytest.raises(lp.LoyaltyError, match="exceeds"):
        lp.reverse("C1", original, 1, "Too much", "admin", "refund-3")


def test_reversal_can_create_negative_balance(program):
    _, reward, _ = program
    lp.process_purchase(purchase(), "integration")
    original = lp.get_member("C1")["entries"][0]["id"]
    h = lp.reserve("C1", reward["id"], "APPT-1", "STORE-1", "service", "hold")
    lp.resolve_hold("C1", h["reservation_id"], "confirm", "service", "confirm", "RO-2", "Applied")
    lp.reverse("C1", original, 3000, "Returned purchase", "admin", "refund")
    assert lp.get_member("C1")["available"] == -2500
    with pytest.raises(lp.LoyaltyError, match="Not enough"):
        lp.reserve("C1", reward["id"], "APPT-2", "STORE-1", "service", "hold-2")


def test_ledger_is_immutable(program):
    lp.process_purchase(purchase(), "integration")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with lp.transaction() as db:
            db.execute("UPDATE entries SET points=90000")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with lp.transaction() as db:
            db.execute("DELETE FROM entries")


def test_future_rule_does_not_hide_historical_rule(program):
    _, _, rule = program
    lp.save_document("rule", rule | {"points": 5, "starts_at": "2099-01-01T00:00:00+00:00"}, "marketing")
    assert lp.process_purchase(purchase(), "integration")["points"] == 3000


def test_preview_matches_post_and_rounds_down(program):
    event = purchase(eligible_cents=17599)
    assert lp.preview(event)["points"] == 175
    assert lp.process_purchase(event, "integration")["points"] == 175


def test_failed_event_retry_after_enrollment(program):
    event = purchase(customer_id="C3")
    assert lp.process_purchase(event, "integration")["status"] == "failed"
    lp.enroll("C3", "New customer", "admin", "enroll-3", "1")
    assert lp.retry_event("dms:RO-1", "admin")["points"] == 3000
    assert lp.retry_event("dms:RO-1", "admin")["points"] == 3000
    assert lp.get_member("C3")["posted"] == 3000


def test_campaign_caps_and_base_bonus_traceability(program):
    campaign = lp.save_document("campaign", dict(name="Visit bonus", status="active", trigger="service",
         calculation="fixed", points=500, member_limit=1, points_cap=500), "marketing")
    assert lp.process_purchase(purchase(campaign_id=campaign["id"]), "integration")["points"] == 3500
    result = lp.process_purchase(purchase(source_id="RO-2", campaign_id=campaign["id"]), "integration")
    assert result["status"] == "failed"
    assert lp.get_member("C1")["posted"] == 3500
    assert {e["kind"] for e in lp.get_member("C1")["entries"]} == {"earn", "bonus"}


def test_program_pauses_and_location_restriction(program):
    config, reward, _ = program
    lp.adjust("C1", 3000, "Opening", "admin", "opening")
    with pytest.raises(lp.LoyaltyError, match="location"):
        lp.reserve("C1", reward["id"], "A1", "OTHER", "service", "hold")
    lp.save_document("program", config | {"earning_enabled": False}, "admin")
    assert lp.process_purchase(purchase(), "integration")["status"] == "failed"


def test_configuration_conflict_and_validation(program):
    config, _, _ = program
    lp.save_document("program", config | {"name":"New"}, "admin")
    with pytest.raises(lp.LoyaltyError, match="changed"):
        lp.save_document("program", config, "admin")
    with pytest.raises(lp.LoyaltyError, match="whole number"):
        lp.save_document("reward", dict(name="Bad",status="active",point_cost=True,department="Service"),"admin")


def test_migration_once_and_customer_safe_projection(program):
    lp.enroll("C3", "Legacy", "admin", "migration-1", "1", legacy_points=2500)
    lp.enroll("C3", "Legacy", "admin", "migration-2", "1", legacy_points=2500)
    assert lp.get_member("C3")["posted"] == 2500
    lp.adjust("C3", 10, "Private internal note", "admin", "support")
    view = lp.customer_view("C3")
    assert "Private internal note" not in str(view)
    assert "actor" not in view["member"]["entries"][0]
    assert lp.legacy_member("C3")["points_balance"] == 2510
    with pytest.raises(lp.LoyaltyError, match="Legacy writes"):
        lp.guard_legacy_write()


def test_tenant_storage_isolation(program, tmp_path, monkeypatch):
    lp.adjust("C1", 500, "Opening", "admin", "opening")
    monkeypatch.setenv("DEALEROS_STORAGE_DIR", str(tmp_path / "other-dealership"))
    assert lp.workspace()["members"] == []
    with pytest.raises(lp.LoyaltyError, match="not enrolled"):
        lp.get_member("C1")


def client_for(role):
    from api.routers.loyalty_program import router, staff
    app = FastAPI()
    app.include_router(router)
    if role:
        app.dependency_overrides[staff] = lambda: {"role": role, "employee_id": "EMP-1"}
    return TestClient(app)


def test_routes_require_staff_and_limit_adjustments(program):
    assert client_for(None).get("/loyalty/program/workspace").status_code == 401
    client = client_for("MARKETING")
    assert client.get("/loyalty/program/workspace").status_code == 200
    assert client.post("/loyalty/program/members/C1/adjust", json={"request_key":"x","points":50,"reason":"Test"}).status_code == 403
    assert client_for("ADMIN").post("/loyalty/program/members/C1/adjust", json={"request_key":"x","points":50,"reason":"Test"}).status_code == 200


def test_public_customer_gate_remains_closed(program):
    client = client_for(None)
    for method, path in [("get", ""), ("post", "/enroll"), ("post", "/reserve")]:
        response = getattr(client, method)("/public/garage/loyalty"+path, headers={"Authorization":"Bearer former-simulation-token"})
        assert response.status_code == 503
        assert "available" in response.json()["detail"]


def test_unknown_appointment_cannot_reserve(program):
    _, reward, _ = program
    response = client_for("SERVICE").post("/loyalty/program/members/C1/reserve", json={
        "request_key":"hold", "reward_id":reward["id"], "appointment_id":"NOT-REAL", "location":"STORE-1"})
    assert response.status_code == 409
