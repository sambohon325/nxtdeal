"""
core/menu_api.py -- thin API layer over core/menu_catalog.py + core/menu_data.py,
imported directly into api/app.py's GET /menu/catalog and GET /menu/data route
handlers, matching this codebase's established core/*.py (business logic) +
core/*_api.py (thin route layer) convention (see core/workflow_tab_data_api.py for the
precedent this follows).
"""

from core.menu_catalog import get_department_menu
from core.menu_data import get_menu_data


def get_department_menu_api(department):
    return {"department": department, "items": get_department_menu(department)}


def get_menu_data_api(role, department, item_key, query=None):
    return get_menu_data(role, department, item_key, query)
