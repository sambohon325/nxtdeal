"""Server-side release boundaries for workflows that currently simulate outcomes.

These workflows have no reviewed production implementation yet. No request field,
stored verification tier or provider registration can enable them. Demo mode is the
existing isolated, non-persistent deployment mode, never a client preference.
"""

from core.json_graph_repository import demo_persistence_disabled

_WORKFLOWS = {
    "credit_decisioning": "Credit report access and automated decisions require reviewed authorization, provider and decision procedures.",
    "accounting_sync": "Accounting synchronization requires reviewed receipt provenance and sale posting rules.",
    "financial_simulation": "Sample accounting entries and bank feeds are available only in an isolated demo.",
    "bank_reconciliation": "Bank reconciliation requires a verified bank feed and reviewed matching evidence.",
    "customer_verification": "Customer verification requires a reviewed identity and contact verification service.",
    "electronic_payments": "Electronic payment processing requires a reviewed processor and verified settlement handling.",
    "automatic_payments": "Automatic payments require reviewed authorizations, scheduling and settlement handling.",
    "trial_vehicle_release": "Trial vehicle release requires reviewed identity, insurance and deposit evidence.",
    "insurance_verification": "Insurance verification requires a reviewed provider and verified coverage evidence.",
}


def workflow_readiness():
    return {name: {
        "status": "sample_data_only" if demo_persistence_disabled() else "unavailable",
        "production_enabled": False,
        "reason": reason,
    } for name, reason in _WORKFLOWS.items()}


def simulation_block(workflow, *, external_dispatch=False):
    if workflow not in _WORKFLOWS:
        return {"error": "Unknown workflow readiness scope.", "code": "unknown_workflow", "blocked": True}
    if demo_persistence_disabled() and not external_dispatch:
        return None
    return {
        "error": _WORKFLOWS[workflow] + " Sample behavior is available only in the isolated demo.",
        "code": "workflow_not_ready",
        "blocked": True,
        "workflow": workflow,
    }
