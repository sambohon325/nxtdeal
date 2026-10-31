"""
Quick Vehicle intake (2026-07-13, session 47) -- the Inventory half of the
per-department "native quick-entry" ask: a trade-in or auction pickup needs to land on
the lot's graph the moment it physically arrives, not after a CSV re-import. Produces a
Vehicle entity with the exact same attribute shape imports/inventory_import.py's CSV
path writes (VIN/Year/Make/Model/Trim/Color/Mileage/Condition/Price/Cost/StockNumber/
Lot/DateSold), so a manually-added vehicle is indistinguishable from an imported one to
every dashboard/profile view that already reads those keys.
"""

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.registry import AmbiguousVehicleIdentity

VALID_CONDITIONS = ["New", "Used"]
VALID_LOTS = ["Franchise New/Used", "BHPH Used Lot"]


def create_vehicle(vin, year, make, model, trim, color, mileage, condition, price, cost, stock_number, lot):

    try:
        existing = registry.find_vehicle(vin, require_unique=True)
    except AmbiguousVehicleIdentity as exc:
        return None, str(exc)

    if existing:
        return None, "A vehicle with this VIN already exists"

    entity_id = id_generator.generate("VEH")

    vehicle = Entity(
        id=entity_id,
        entity_type=VEHICLE,
        attributes={
            "VIN": vin,
            "Year": year,
            "Make": make,
            "Model": model,
            "Trim": trim or "",
            "Color": color or "",
            "Mileage": mileage,
            "Condition": condition,
            "Price": price,
            "Cost": cost,
            "StockNumber": stock_number or "",
            "Lot": lot,
            "DateSold": "",
        },
    )

    ledger.add_entity(vehicle)

    registry.register_vehicle(vin, entity_id)

    save_graph(GRAPH_PATH)

    return vehicle, None
