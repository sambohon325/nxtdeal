"""
core/data_connections_api.py — ACL layer for the integration platform (session 37).
ADMIN/OPERATIONS only, same tier as Department Intelligence/bot coverage -- api/app.py imports these
functions directly into route handlers, same convention every other `*_api.py` module
in this codebase follows.
"""

from core.permissions import ADMIN, OPERATIONS

from core.data_connections import (
    create_connection,
    list_connections,
    ingest_csv,
    test_api_connection,
)

from core.prediction import (
    DEPARTMENTS,
    predict_all_horizons,
    all_departments_readiness,
    timeline as prediction_timeline,
)

from core.entities import Entity
from core.entity_types import CONNECTION
from core.compliance import evaluate

CONNECTION_ROLES = (ADMIN, OPERATIONS)

_FORBIDDEN = {
    "error": "You don't have access to data connections with your current role -- "
    "Admin or Operations can configure integrations."
}


def create_connection_api(role, name, connection_type, department, created_by, endpoint_url=None):

    if role not in CONNECTION_ROLES:
        return _FORBIDDEN

    # Compliance agent (session 38) -- GLBA Safeguards Rule check on the pending
    # connection's endpoint BEFORE it's ever created (a lightweight, unpersisted
    # Entity, since nothing exists on the graph yet for this action). No
    # ComplianceAlert is created here (there's no real entity to attach one to) --
    # this is a straightforward creation-time validation, distinct from the
    # already-exists gates on deals/campaigns/assets/websites, which do create an
    # alert + notify since those entities are real and visible elsewhere.
    precheck = Entity(
        id="(not yet created)",
        entity_type=CONNECTION,
        attributes={"connection_type": connection_type, "endpoint_url": endpoint_url},
    )
    result = evaluate("connection_create", precheck)

    if not result["passed"]:
        return {
            "error": "Compliance check failed -- this connection can't be created until the issue(s) below are corrected.",
            "compliance_violations": result["violations"],
            "notice": result["notice"],
        }

    return create_connection(name, connection_type, department, created_by, endpoint_url)


def list_connections_api(role, department=None):

    if role not in CONNECTION_ROLES:
        return _FORBIDDEN

    return {"connections": list_connections(department)}


def ingest_csv_api(role, connection_id, filename, file_bytes, csv_kind=None):

    if role not in CONNECTION_ROLES:
        return _FORBIDDEN

    return ingest_csv(connection_id, filename, file_bytes, csv_kind)


def test_api_connection_api(role, connection_id):

    if role not in CONNECTION_ROLES:
        return _FORBIDDEN

    return test_api_connection(connection_id)


def readiness_predictions_api():
    """Every department's full prediction set (all 4 horizons) plus the go-live gate --
    backs the readiness page's main view. Deliberately open to ANY authenticated role,
    unlike connection management above -- Sam: "everyone can see tomorrow, a week, a
    month, a quarter" -- predictions are read-only, non-sensitive forward-looking
    counts (units/ROs/contracts/leads), not the compensation-adjacent data
    core/employee_value.py gates more tightly, and not the integration configuration
    this module's other functions gate to ADMIN/OPERATIONS."""

    return {
        "departments": [
            {
                "department": department,
                "readiness": readiness,
                "predictions": predict_all_horizons(department),
            }
            for department, readiness in zip(DEPARTMENTS, all_departments_readiness())
        ]
    }


def prediction_timeline_api(department):
    """The Reporting tab's prediction-horizon-slider data (session 71) -- last week /
    current / tomorrow / next week / next month / next quarter for one department.
    Open to any role, same reasoning as readiness_predictions_api() above: read-only,
    non-sensitive forward-looking counts, not the compensation-adjacent or integration-
    configuration data this module gates more tightly elsewhere. Returns an honest
    "not available" shape (not an error) for a department with no real prediction
    source -- see core/prediction.py's DEPARTMENTS list."""

    result = prediction_timeline(department)

    if result is None:
        return {
            "department": department,
            "available": False,
            "note": (
                f"No predictive scoring source exists yet for {department} -- "
                "core/prediction.py only tracks sales/service/finance/parts/marketing."
            ),
        }

    result["available"] = True
    return result
