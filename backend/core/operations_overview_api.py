"""
Thin pass-through layer for core/operations_overview.py, matching
core/operations_menu.py's own established convention: no hard top-level role
gate (any authenticated role can call it), since the real ACL enforcement
already happens inside the reused sub-functions (list_alerts_api, etc.), which
degrade gracefully per-field for a role without access rather than blocking the
whole response -- same behavior confirmed for operations_menu.py's own
overview()/tasks() since session 60.
"""

from core.operations_overview import get_operations_overview


def get_operations_overview_api(role):
    return get_operations_overview(role)
