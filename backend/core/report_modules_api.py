"""
core/report_modules_api.py -- thin API layer over core/report_modules.py, imported
directly into api/app.py's GET /report-modules and GET /overview-modules route
handlers, matching this codebase's established core/*.py (business logic) +
core/*_api.py (thin route layer) convention (see core/menu_api.py for the precedent
this follows). get_overview_modules_api added session 77.
"""

from core.report_modules import get_report_modules, get_overview_modules


def get_report_modules_api(role, department):
    return get_report_modules(role, department)


def get_overview_modules_api(role, employee_id, department):
    return get_overview_modules(role, employee_id, department)
