"""
Quick Service ticket intake (2026-07-13, session 47) -- the Service half of the
per-department "native quick-entry" ask: a technician logging a job while standing at
the vehicle, not typing a chat sentence. Produces a ServiceRecord entity with the exact
same attribute shape imports/service_import.py's CSV path writes (ServiceNumber/
CustomerID/VIN/Description/ServiceDate/Mileage/Cost/PartsCost/LaborHours/PayType/
Status/Technician), so it's indistinguishable from an imported one to
core/employee_value.py's real per-technician attribution and every dashboard. Technician
is always the creating employee's real graph id (already correct -- no CSV business-key
resolution needed, since this endpoint's caller IS the technician).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import SERVICE_RECORD
from core.relationships import Relationship
from core.relationship_types import HAS_SERVICE_RECORD, AUTHORIZED
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

VALID_PAY_TYPES = ["Warranty", "Internal", "Customer Pay"]
VALID_STATUSES = ["In Progress", "Completed"]


def _now_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def create_service_record(
    technician_id,
    vin,
    description,
    pay_type,
    status="Completed",
    customer_id=None,
    mileage=None,
    cost=None,
    parts_cost=None,
    labor_hours=None,
):

    service_id = id_generator.generate("SRV")

    attributes = {
        "ServiceNumber": service_id,
        "CustomerID": customer_id or "",
        "VIN": vin or "",
        "Description": description,
        "ServiceDate": _now_date(),
        "Mileage": mileage or "",
        "Cost": cost or "",
        "PartsCost": parts_cost or "",
        "LaborHours": labor_hours or "",
        "PayType": pay_type,
        "Status": status,
        "Technician": technician_id,
    }

    record = Entity(id=service_id, entity_type=SERVICE_RECORD, attributes=attributes)

    ledger.add_entity(record)

    if customer_id:

        customer_entity_id = registry.find_customer(customer_id)

        if customer_entity_id:

            ledger.add_relationship(
                Relationship(
                    source_id=customer_entity_id,
                    target_id=service_id,
                    relationship_type=AUTHORIZED,
                )
            )

    if vin:

        vehicle_id = registry.find_vehicle(vin)

        if vehicle_id:

            ledger.add_relationship(
                Relationship(
                    source_id=vehicle_id,
                    target_id=service_id,
                    relationship_type=HAS_SERVICE_RECORD,
                )
            )

    save_graph(GRAPH_PATH)

    return record
