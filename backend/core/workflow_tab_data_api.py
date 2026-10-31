"""
core/workflow_tab_data_api.py -- thin API layer over core/workflow_tab_data.py's engine,
imported directly into api/app.py's GET /workflows/tab-data route handler, matching this
codebase's established core/*.py (business logic) + core/*_api.py (thin route layer)
convention (see core/workflow_tracking.py + core/workflow_tracking_api.py for the
precedent this follows).
"""

from core.workflow_tab_data import get_tab_data


def get_tab_data_api(role, workflow_key, linked_entity_id=None):

    from core.administration_access import system_admin_context
    if workflow_key in ("administration.audit_monitoring", "administration.vendor_management") and not system_admin_context.get():
        return {"error": "NXTDeal system administrator access required"}
    return get_tab_data(role, workflow_key, linked_entity_id)
