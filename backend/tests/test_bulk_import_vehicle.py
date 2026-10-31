"""
Vehicle / inventory CSV import (Freemium roadmap, Phase 3, 2026-08-03). Extends the existing
lead/customer bulk importer with a 'vehicle' target: self-serve, credential-free inventory upload,
deduped by VIN + stock number, with best-effort offline VIN decode backfill. Run from backend/ with
`pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import bulk_import as bi


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


HEADERS = ["VIN", "Stock #", "Year", "Make", "Model", "Asking Price", "Odometer"]


def _rows():
    return [
        {"VIN": "1FTFW1ET5DFA12345", "Stock #": "A100", "Year": "2019", "Make": "Ford", "Model": "F-150", "Asking Price": "32000", "Odometer": "41000"},
        {"VIN": "1FTFW1ET5DFA12345", "Stock #": "A100", "Year": "2019", "Make": "Ford", "Model": "F-150", "Asking Price": "32000", "Odometer": "41000"},  # dup VIN
        {"Stock #": "A101", "Year": "2020", "Make": "Toyota", "Model": "Camry", "Asking Price": "24000"},  # stock only, ok
        {"Year": "2021", "Make": "Honda"},  # error: no VIN or stock
    ]


def test_vehicle_mapping_autodetects():
    m = bi.suggest_mapping(HEADERS, "vehicle")
    assert m["VIN"] == "vin"
    assert m["Stock #"] == "stock_number"
    assert m["Asking Price"] == "price"
    assert m["Odometer"] == "mileage"


def test_vehicle_plan_dedupes_and_flags_errors():
    m = bi.suggest_mapping(HEADERS, "vehicle")
    plan = bi.plan_import(_rows(), m, "vehicle")
    assert plan["will_create"] == 2
    assert plan["duplicates"] == 1  # second row, dup VIN within batch
    assert plan["errors"] == 1      # row with no VIN or stock


def test_vehicle_run_creates_real_vehicles():
    m = bi.suggest_mapping(HEADERS, "vehicle")
    res = bi.run_import(_rows(), m, "vehicle", "EMP-1")
    assert res["created_count"] == 2 and res["skipped_count"] == 1 and res["error_count"] == 1
    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE]
    assert len(vehicles) == 2
    vins = {v.attributes.get("VIN") for v in vehicles}
    assert "1FTFW1ET5DFA12345" in vins


def test_vehicle_import_dedupes_against_existing_lot():
    ledger.add_entity(Entity(id="VEH-EXIST", entity_type=VEHICLE, attributes={"VIN": "1FTFW1ET5DFA12345"}))
    m = bi.suggest_mapping(HEADERS, "vehicle")
    res = bi.run_import(_rows(), m, "vehicle", "EMP-1")
    # the F-150 VIN already exists -> only the Camry (stock A101) is new
    assert res["created_count"] == 1


def test_bad_vin_length_is_error():
    m = {"VIN": "vin", "Stock #": "stock_number"}
    rows = [{"VIN": "SHORTVIN", "Stock #": "B1"}]
    plan = bi.plan_import(rows, m, "vehicle")
    assert plan["errors"] == 1


def test_lead_customer_import_unaffected():
    # the existing contact importer path must be byte-for-byte unchanged behavior
    m = {"first": "first_name", "last": "last_name", "email": "email"}
    rows = [{"first": "Jane", "last": "Doe", "email": "jane@x.com"}]
    res = bi.run_import(rows, m, "customer", "EMP-1")
    assert res["created_count"] == 1
