"""
Tests for core/vehicle_holds.py + core/vehicle_holds_api.py -- the real
Reservation/Hold mechanism for Sales' Inventory item (session 99 follow-up).
A VehicleHold is a short-lived, ordinary graph entity whose expiry is computed
live on every read (now vs. expires_at), not via a background scheduler.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, CUSTOMER, LEAD, VEHICLE_HOLD
from core import vehicle_holds
from core import vehicle_holds_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(vehicle_holds, "save_graph", lambda filepath: None)


_HOLD_ROLES = (ADMIN, OPERATIONS, SALES)
_HOLD_DENIED_ROLES = (MARKETING, SERVICE, FINANCE)

# list_active_holds_api is gated via can_access_entity(role, VEHICLE), and
# ENTITY_ACCESS[VEHICLE] includes every one of this codebase's 6 real roles --
# so there is no denied role among the standard set for that one function.
_ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _iso_minutes_from_now(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _iso_minutes_ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _add_vehicle(vehicle_id="VEH-1", date_sold=None, make="Ford", model="F-150"):
    attrs = {"Make": make, "Model": model, "Year": "2024", "Price": "35000"}
    if date_sold:
        attrs["DateSold"] = date_sold
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes={"FirstName": first, "LastName": last}))
    return customer_id


def _add_lead(lead_id="LEAD-1", first="Alex", last="Prospect"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={"FirstName": first, "LastName": last}))
    return lead_id


def _add_raw_hold(hold_id="HOLD-RAW-1", vehicle_id="VEH-1", held_by="EMP-1", status="active",
                   expires_at="__DEFAULT__", placed_at=None):
    """Directly injects a VehicleHold entity into the ledger, bypassing place_hold(),
    so tests can construct edge-case states (missing/malformed expires_at, an
    already-expired hold, a specific placed_at for sort-order checks) that the real
    place_hold() function can never itself produce."""
    if expires_at == "__DEFAULT__":
        expires_at = _iso_minutes_from_now(60)
    attrs = {
        "vehicle_id": vehicle_id,
        "held_by": held_by,
        "customer_id": None,
        "lead_id": None,
        "notes": "",
        "status": status,
        "placed_at": placed_at or datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "released_at": None,
        "released_by": None,
    }
    ledger.add_entity(Entity(id=hold_id, entity_type=VEHICLE_HOLD, attributes=attrs))
    return hold_id


# ---------------------------------------------------------------------------
# place_hold
# ---------------------------------------------------------------------------

class TestPlaceHold:
    def test_rejects_unknown_vehicle(self):
        result = vehicle_holds.place_hold("VEH-NOPE", "EMP-1")
        assert "error" in result

    def test_rejects_non_vehicle_entity(self):
        _add_customer("VEH-1")  # same id, wrong entity_type
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        assert "error" in result

    def test_rejects_already_sold_vehicle(self):
        _add_vehicle("VEH-1", date_sold="2026-01-01")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        assert "error" in result
        assert "already sold" in result["error"]

    def test_succeeds_on_a_valid_unsold_vehicle(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        assert isinstance(result, Entity)
        assert result.entity_type == VEHICLE_HOLD
        assert result.id.startswith("HOLD")
        assert result.attributes["vehicle_id"] == "VEH-1"
        assert result.attributes["held_by"] == "EMP-1"
        assert result.attributes["status"] == "active"
        assert result.attributes["released_at"] is None
        assert result.attributes["released_by"] is None

    def test_persists_the_new_hold_in_the_ledger(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        stored = ledger.get_entity(result.id)
        assert stored is not None
        assert stored.entity_type == VEHICLE_HOLD

    def test_notes_default_to_empty_string(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        assert result.attributes["notes"] == ""

    def test_notes_are_stored_when_provided(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", notes="Customer coming back at 5pm")
        assert result.attributes["notes"] == "Customer coming back at 5pm"

    def test_rejects_a_conflicting_hold_from_a_different_employee(self):
        _add_vehicle("VEH-1")
        vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-2")
        assert "error" in result
        assert "already on hold" in result["error"]

    def test_same_employee_re_holding_their_own_active_hold_is_allowed(self):
        _add_vehicle("VEH-1")
        first = vehicle_holds.place_hold("VEH-1", "EMP-1")
        second = vehicle_holds.place_hold("VEH-1", "EMP-1")
        assert isinstance(second, Entity)
        assert second.id != first.id

    def test_a_released_hold_does_not_block_a_new_hold_by_another_employee(self):
        _add_vehicle("VEH-1")
        first = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(first.id, "EMP-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-2")
        assert isinstance(result, Entity)

    def test_an_expired_hold_does_not_block_a_new_hold_by_another_employee(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-EXPIRED", vehicle_id="VEH-1", held_by="EMP-1", status="active",
                       expires_at=_iso_minutes_ago(5))
        result = vehicle_holds.place_hold("VEH-1", "EMP-2")
        assert isinstance(result, Entity)

    def test_rejects_an_unknown_customer_id(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", customer_id="CUST-NOPE")
        assert "error" in result

    def test_rejects_a_customer_id_pointing_at_the_wrong_entity_type(self):
        _add_vehicle("VEH-1")
        _add_lead("CUST-1")  # same id, wrong entity_type for a Customer lookup
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", customer_id="CUST-1")
        assert "error" in result

    def test_accepts_a_valid_customer_id(self):
        _add_vehicle("VEH-1")
        _add_customer("CUST-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", customer_id="CUST-1")
        assert isinstance(result, Entity)
        assert result.attributes["customer_id"] == "CUST-1"

    def test_rejects_an_unknown_lead_id(self):
        _add_vehicle("VEH-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", lead_id="LEAD-NOPE")
        assert "error" in result

    def test_rejects_a_lead_id_pointing_at_the_wrong_entity_type(self):
        _add_vehicle("VEH-1")
        _add_customer("LEAD-1")  # same id, wrong entity_type for a Lead lookup
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", lead_id="LEAD-1")
        assert "error" in result

    def test_accepts_a_valid_lead_id(self):
        _add_vehicle("VEH-1")
        _add_lead("LEAD-1")
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", lead_id="LEAD-1")
        assert isinstance(result, Entity)
        assert result.attributes["lead_id"] == "LEAD-1"

    def test_default_duration_is_24_hours(self):
        _add_vehicle("VEH-1")
        before = datetime.now(timezone.utc)
        result = vehicle_holds.place_hold("VEH-1", "EMP-1")
        expires = datetime.fromisoformat(result.attributes["expires_at"])
        delta_hours = (expires - before).total_seconds() / 3600
        assert 23.9 <= delta_hours <= 24.1

    def test_a_zero_duration_falls_back_to_the_default_since_it_is_falsy(self):
        _add_vehicle("VEH-1")
        before = datetime.now(timezone.utc)
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", duration_hours=0)
        expires = datetime.fromisoformat(result.attributes["expires_at"])
        delta_hours = (expires - before).total_seconds() / 3600
        assert 23.9 <= delta_hours <= 24.1

    def test_a_negative_duration_is_clamped_to_one_hour(self):
        _add_vehicle("VEH-1")
        before = datetime.now(timezone.utc)
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", duration_hours=-50)
        expires = datetime.fromisoformat(result.attributes["expires_at"])
        delta_hours = (expires - before).total_seconds() / 3600
        assert 0.9 <= delta_hours <= 1.1

    def test_an_excessive_duration_is_clamped_to_the_max(self):
        _add_vehicle("VEH-1")
        before = datetime.now(timezone.utc)
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", duration_hours=10000)
        expires = datetime.fromisoformat(result.attributes["expires_at"])
        delta_hours = (expires - before).total_seconds() / 3600
        assert 167.9 <= delta_hours <= 168.1

    def test_a_duration_within_range_is_respected(self):
        _add_vehicle("VEH-1")
        before = datetime.now(timezone.utc)
        result = vehicle_holds.place_hold("VEH-1", "EMP-1", duration_hours=5)
        expires = datetime.fromisoformat(result.attributes["expires_at"])
        delta_hours = (expires - before).total_seconds() / 3600
        assert 4.9 <= delta_hours <= 5.1


# ---------------------------------------------------------------------------
# release_hold
# ---------------------------------------------------------------------------

class TestReleaseHold:
    def test_rejects_unknown_hold(self):
        result = vehicle_holds.release_hold("HOLD-NOPE", "EMP-1")
        assert "error" in result
        assert result["error"] == "Hold not found"

    def test_rejects_a_hold_id_pointing_at_the_wrong_entity_type(self):
        _add_vehicle("HOLD-1")  # same id, wrong entity_type
        result = vehicle_holds.release_hold("HOLD-1", "EMP-1")
        assert "error" in result
        assert result["error"] == "Hold not found"

    def test_releases_an_active_hold(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds.release_hold(hold.id, "EMP-1")
        assert isinstance(result, Entity)
        assert result.attributes["status"] == "released"
        assert result.attributes["released_by"] == "EMP-1"
        assert result.attributes["released_at"] is not None

    def test_a_different_employee_can_release_someone_elses_hold(self):
        # release_hold() itself has no ownership check -- that gate, if any, lives
        # at the API/role layer, not the core function.
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds.release_hold(hold.id, "EMP-2")
        assert isinstance(result, Entity)
        assert result.attributes["released_by"] == "EMP-2"

    def test_rejects_releasing_an_already_released_hold(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(hold.id, "EMP-1")
        result = vehicle_holds.release_hold(hold.id, "EMP-1")
        assert "error" in result
        assert "released" in result["error"]

    def test_rejects_releasing_an_expired_hold(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-EXPIRED", vehicle_id="VEH-1", held_by="EMP-1", status="active",
                       expires_at=_iso_minutes_ago(5))
        result = vehicle_holds.release_hold("HOLD-EXPIRED", "EMP-1")
        assert "error" in result
        assert "expired" in result["error"]


# ---------------------------------------------------------------------------
# _is_expired / _effective_status edge cases (via get_active_hold, since the
# helpers are private -- exercised through the real code path that relies on
# them)
# ---------------------------------------------------------------------------

class TestEffectiveStatusEdgeCases:
    def test_a_hold_with_no_expires_at_never_expires(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-1", vehicle_id="VEH-1", held_by="EMP-1", status="active", expires_at=None)
        active = vehicle_holds.get_active_hold("VEH-1")
        assert active is not None
        assert active.id == "HOLD-1"

    def test_a_hold_with_a_malformed_expires_at_string_is_treated_as_not_expired(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-1", vehicle_id="VEH-1", held_by="EMP-1", status="active",
                       expires_at="not-a-real-timestamp")
        active = vehicle_holds.get_active_hold("VEH-1")
        assert active is not None
        assert active.id == "HOLD-1"

    def test_a_naive_datetime_expires_at_in_the_past_is_treated_as_expired(self):
        naive_past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-1", vehicle_id="VEH-1", held_by="EMP-1", status="active",
                       expires_at=naive_past)
        active = vehicle_holds.get_active_hold("VEH-1")
        assert active is None

    def test_a_released_status_wins_even_if_not_yet_expired(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-1", vehicle_id="VEH-1", held_by="EMP-1", status="released",
                       expires_at=_iso_minutes_from_now(60))
        active = vehicle_holds.get_active_hold("VEH-1")
        assert active is None


# ---------------------------------------------------------------------------
# get_active_hold
# ---------------------------------------------------------------------------

class TestGetActiveHold:
    def test_returns_none_when_no_holds_exist(self):
        _add_vehicle("VEH-1")
        assert vehicle_holds.get_active_hold("VEH-1") is None

    def test_returns_the_active_hold(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        active = vehicle_holds.get_active_hold("VEH-1")
        assert active is not None
        assert active.id == hold.id

    def test_returns_none_when_only_a_released_hold_exists(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(hold.id, "EMP-1")
        assert vehicle_holds.get_active_hold("VEH-1") is None

    def test_returns_none_when_only_an_expired_hold_exists(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-EXPIRED", vehicle_id="VEH-1", status="active", expires_at=_iso_minutes_ago(5))
        assert vehicle_holds.get_active_hold("VEH-1") is None

    def test_ignores_holds_on_other_vehicles(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        vehicle_holds.place_hold("VEH-2", "EMP-1")
        assert vehicle_holds.get_active_hold("VEH-1") is None


# ---------------------------------------------------------------------------
# list_active_holds
# ---------------------------------------------------------------------------

class TestListActiveHolds:
    def test_empty_when_no_holds(self):
        assert vehicle_holds.list_active_holds() == []

    def test_returns_only_active_holds_across_vehicles(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        _add_vehicle("VEH-3")

        active_hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        released_hold = vehicle_holds.place_hold("VEH-2", "EMP-1")
        vehicle_holds.release_hold(released_hold.id, "EMP-1")
        _add_raw_hold("HOLD-EXPIRED", vehicle_id="VEH-3", status="active", expires_at=_iso_minutes_ago(5))

        result = vehicle_holds.list_active_holds()
        assert [h.id for h in result] == [active_hold.id]


# ---------------------------------------------------------------------------
# list_my_holds
# ---------------------------------------------------------------------------

class TestListMyHolds:
    def test_filters_by_held_by(self):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        mine = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.place_hold("VEH-2", "EMP-2")

        result = vehicle_holds.list_my_holds("EMP-1")
        assert [h.id for h in result] == [mine.id]

    def test_excludes_inactive_holds_by_default(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(hold.id, "EMP-1")

        result = vehicle_holds.list_my_holds("EMP-1")
        assert result == []

    def test_include_inactive_true_returns_released_holds_too(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(hold.id, "EMP-1")

        result = vehicle_holds.list_my_holds("EMP-1", include_inactive=True)
        assert [h.id for h in result] == [hold.id]

    def test_sorted_most_recently_placed_first(self):
        _add_vehicle("VEH-1")
        _add_raw_hold("HOLD-OLD", vehicle_id="VEH-1", held_by="EMP-1",
                       placed_at=_iso_minutes_ago(60))
        _add_raw_hold("HOLD-NEW", vehicle_id="VEH-1", held_by="EMP-1",
                       placed_at=_iso_minutes_ago(5))

        result = vehicle_holds.list_my_holds("EMP-1", include_inactive=True)
        assert [h.id for h in result] == ["HOLD-NEW", "HOLD-OLD"]

    def test_returns_empty_for_an_employee_with_no_holds(self):
        assert vehicle_holds.list_my_holds("EMP-GHOST") == []


# ---------------------------------------------------------------------------
# ACL sweep -- core/vehicle_holds_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _HOLD_DENIED_ROLES)
    def test_place_hold_api_denied(self, role):
        _add_vehicle("VEH-1")
        result = vehicle_holds_api.place_hold_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _HOLD_ROLES)
    def test_place_hold_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        result = vehicle_holds_api.place_hold_api(role, "EMP-1", "VEH-1")
        assert "error" not in result
        assert result["status"] == "active"

    @pytest.mark.parametrize("role", _HOLD_DENIED_ROLES)
    def test_release_hold_api_denied(self, role):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds_api.release_hold_api(role, "EMP-1", hold.id)
        assert "error" in result

    @pytest.mark.parametrize("role", _HOLD_ROLES)
    def test_release_hold_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds_api.release_hold_api(role, "EMP-1", hold.id)
        assert "error" not in result
        assert result["status"] == "released"

    @pytest.mark.parametrize("role", _ALL_ROLES)
    def test_list_active_holds_api_allowed_for_every_real_role(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds_api.list_active_holds_api(role)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_list_active_holds_api_denies_an_unrecognized_role(self):
        result = vehicle_holds_api.list_active_holds_api("NOT_A_REAL_ROLE")
        assert "error" in result

    @pytest.mark.parametrize("role", _HOLD_DENIED_ROLES)
    def test_list_my_holds_api_denied(self, role):
        result = vehicle_holds_api.list_my_holds_api(role, "EMP-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _HOLD_ROLES)
    def test_list_my_holds_api_allowed(self, role):
        ledger.reset()
        _add_vehicle("VEH-1")
        vehicle_holds.place_hold("VEH-1", "EMP-1")
        result = vehicle_holds_api.list_my_holds_api(role, "EMP-1")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_list_my_holds_api_include_inactive_passthrough(self):
        _add_vehicle("VEH-1")
        hold = vehicle_holds.place_hold("VEH-1", "EMP-1")
        vehicle_holds.release_hold(hold.id, "EMP-1")

        result = vehicle_holds_api.list_my_holds_api(ADMIN, "EMP-1", include_inactive=True)
        assert len(result) == 1
        assert result[0]["status"] == "released"

        result_default = vehicle_holds_api.list_my_holds_api(ADMIN, "EMP-1")
        assert result_default == []
