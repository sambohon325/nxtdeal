"""
core/graph_explore_api.py -- thin API layer over core/graph_explore.py, imported
directly into api/app.py's GET /entity/{entity_id}/explore route handler, same
"no service layer indirection" convention every other `*_api.py` module in this
codebase follows.
"""

from core.graph_explore import explore_entity


def explore_entity_api(role, employee_id, entity_id, depth=None):
    return explore_entity(entity_id, role, employee_id, depth=depth)
