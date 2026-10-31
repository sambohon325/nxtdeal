"""Thin ACL layer for core/consulting_engine.py -- same "no service-layer
indirection, one uniform {"error": ...} error contract" convention every other
*_api.py module in this codebase follows.

VIEW_ROLES is deliberately narrow (ADMIN, OPERATIONS): the Consulting Engine is
executive/manager-level strategic consulting that composes whole-store,
cross-department analysis (peer benchmarks, dollar-opportunity sizing, the
Executive Recommendations feed) -- the same executive tier core/network_api.py's
NETWORK_ROLES / core/permissions.py's DASHBOARD_ACCESS["consulting_engine"]
already scope Network's own intelligence to, not the broad cross-department
staff tier core/customer_journey_api.py / core/communications_hub_api.py use.

core/consulting_engine.py never raises for a bad question/department -- it
returns its own {"error": ...} dict -- so this layer only adds the role gate on
top and passes the real result straight through.
"""

from core.consulting_engine import run_consultation, get_consulting_overview

VIEW_ROLES = ("ADMIN", "OPERATIONS")


def run_consultation_api(role, question, department=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to run an AI consultation."}

    try:
        return run_consultation(question, role, department=department)
    except ValueError as exc:
        return {"error": str(exc)}


def get_consulting_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the AI Consulting Engine overview."}

    try:
        return get_consulting_overview(role)
    except ValueError as exc:
        return {"error": str(exc)}
