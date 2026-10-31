"""
Thin API layer for MySales self-accounting (2026-07-24). Every view is keyed to the signed-in
rep (employee_id from the token) and open to any authenticated employee — a rep manages their
OWN money. Validate + call + shape, matching core/*_api.py.
"""

from core import rep_finance


def get_overview_api(employee_id):
    return rep_finance.get_overview(employee_id)


def link_bank_api(employee_id, institution=None):
    return rep_finance.link_bank(employee_id, institution=institution)


def set_budget_api(employee_id, category, limit):
    return rep_finance.set_budget(employee_id, category, limit)


def list_budgets_api(employee_id):
    return {"budgets": rep_finance.list_budgets(employee_id)}


def record_commission_api(employee_id, amount, status="pending", source=None, deal_id=None, date=None):
    return rep_finance.record_commission(
        employee_id, amount, status=status, source=source, deal_id=deal_id, date=date,
    )


def list_commissions_api(employee_id):
    return {"commissions": rep_finance.list_commissions(employee_id)}


def advisor_api(employee_id):
    return {"insights": rep_finance.advisor(employee_id)}
