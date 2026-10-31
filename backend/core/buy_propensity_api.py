"""
ACL layer for Buy-Propensity scoring + enrichment (Phase 1, 2026-07-25). Viewing scores and
the ranking leaderboard is open to any authenticated role (it's operational sales insight,
same posture as core/lead_scoring_api.py). Running enrichment writes to the customer record
and can consume a paid provider, so it's the narrower ADMIN/OPERATIONS/MARKETING tier.
"""

from core import buy_propensity
from core import data_enrichment
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC

VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC)
ENRICH_ROLES = (ADMIN, OPERATIONS, MARKETING)


def compute_propensity_api(role, entity_id):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to propensity scores"}
    return buy_propensity.compute_propensity(entity_id)


def rank_api(role, limit=50, segment="customers"):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to propensity scores"}
    if segment not in ("customers", "leads", "all"):
        return {"error": "segment must be customers, leads, or all"}
    return buy_propensity.rank(limit=limit, segment=segment)


def draft_outreach_api(role, entity_id, channel="email"):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to propensity outreach"}
    return buy_propensity.draft_outreach(entity_id, channel=channel)


def enrich_customer_api(role, employee_id, customer_id):
    if role not in ENRICH_ROLES:
        return {"error": "Admin/Operations/Marketing role required to run enrichment"}
    return data_enrichment.enrich_customer(customer_id)


def get_enrichment_api(role, customer_id):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to enrichment data"}
    return data_enrichment.get_enrichment(customer_id)
