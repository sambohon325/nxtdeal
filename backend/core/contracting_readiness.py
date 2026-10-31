"""Temporary contracting release gate pending reviewed forms and execution evidence.

The existing generator produces a worksheet, not an executable agreement. No
jurisdiction is enabled for production execution. Only the existing isolated,
non-persistent demo deployment may simulate signing and funding. Neither deal
attributes, an admin override nor registering a provider constitutes approval.
"""

from core.json_graph_repository import demo_persistence_disabled


def contracting_readiness():
    return {
        "status": "sample_data_only" if demo_persistence_disabled() else "unavailable",
        "production_enabled": False,
        "enabled_jurisdictions": [],
        "first_review_jurisdiction": "TX",
        "worksheet_available": True,
        "required_evidence": [
            "Form rights and exact version",
            "Jurisdiction and transaction applicability review",
            "Calculation and field mapping validation",
            "Required regulator and lender review",
            "Signature, delivery and record preservation validation",
            "Production security and workflow readiness",
        ],
    }


def execution_block(action, *, external_dispatch=False):
    """Return a normal service error before side effects, or None for a demo action.

External signature delivery stays blocked even in demo mode. This is deliberately
not a production enable switch; a future reviewed scope registry must replace it.
"""
    if demo_persistence_disabled() and not external_dispatch:
        return None
    return {
        "error": (
            "Contract execution is unavailable. The generated summary is an estimate "
            "worksheet, not an approved retail installment contract. Signing and funding "
            "require reviewed forms, calculations and execution controls. Sample signing "
            "and funding are available only in the isolated demo; external signature "
            "delivery is disabled."
        ),
        "code": "contract_execution_not_ready",
        "blocked": True,
        "action": action,
        "readiness": contracting_readiness(),
    }
