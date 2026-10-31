"""
Thin API-layer function for quick Vehicle intake (session 47). Any authenticated role
can log a vehicle arrival -- same "any role creates" precedent as assets/campaigns/deals.
"""

from core.vehicle_intake import create_vehicle, VALID_CONDITIONS, VALID_LOTS


def _serialize(entity):
    return {
        "id": entity.id,
        **entity.attributes,
    }


def create_vehicle_api(vin, year, make, model, trim, color, mileage, condition, price, cost, stock_number, lot):

    if not vin or not make or not model or not year:
        return {"error": "vin, year, make, and model are required"}

    if condition not in VALID_CONDITIONS:
        return {"error": f"condition must be one of {', '.join(VALID_CONDITIONS)}"}

    if lot not in VALID_LOTS:
        return {"error": f"lot must be one of {', '.join(VALID_LOTS)}"}

    vehicle, error = create_vehicle(
        vin, year, make, model, trim, color, mileage, condition, price, cost, stock_number, lot
    )

    if error:
        return {"error": error}

    return _serialize(vehicle)
