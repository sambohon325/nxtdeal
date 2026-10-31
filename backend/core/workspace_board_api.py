"""
core/workspace_board_api.py -- thin API layer over core/workspace_board.py, imported
directly into api/app.py's GET/POST /workspace-board route handlers. No extra ACL beyond
"must be authenticated" (already enforced by api/app.py's _authenticate) -- a Workspace
board is purely personal, per-employee data, same as notification preferences.

Session 76 third follow-up (Sam: "move the pin to knowledge out of the reports and
notes windows and put it into the workspace as a whole... they need to be able to
title it what they want and set viewing permissions") -- get_shared_workspace_board_api
below is the one exception: a *viewer* (not the owner) reading someone else's board,
gated on a real core/knowledge_pins.py 'workspace_board' pin actually having been shared
with them. Without this, "set viewing permissions" on a whole-Workspace pin would just
be a label with no access behind it.
"""

from core.workspace_board import get_board, save_board, add_workspace_item
from core.knowledge_pins import list_pins_for_role


def get_workspace_board_api(employee_id):
    return get_board(employee_id)


def save_workspace_board_api(employee_id, items):
    return save_board(employee_id, items)


def add_workspace_item_api(employee_id, item):
    """Append one grabbed frame to the caller's own board (Workspace grab-all,
    2026-07-23). Purely personal data, so no ACL beyond authentication -- same as
    save_workspace_board_api."""
    return add_workspace_item(employee_id, item)


def get_shared_workspace_board_api(viewer_employee_id, viewer_role, owner_employee_id):
    """A Workspace board is normally personal (see module docstring) -- this is the one
    read path where someone other than the owner can see it, and only because a real
    'workspace_board' Shared Knowledge pin naming owner_employee_id as its ref_id
    actually grants that role/employee visibility. Reuses
    core/knowledge_pins.py's own list_pins_for_role() rather than re-deriving the
    ADMIN-sees-everything / owner-always-sees-their-own-shares rules a second time."""

    if viewer_employee_id == owner_employee_id:
        return get_board(owner_employee_id)

    shared_pins = list_pins_for_role(viewer_role, viewer_employee_id)

    authorized = any(
        p["kind"] == "workspace_board" and p["ref_id"] == owner_employee_id
        for p in shared_pins
    )

    if not authorized:
        return {"error": "Forbidden: this Workspace hasn't been shared with you."}

    return get_board(owner_employee_id)
