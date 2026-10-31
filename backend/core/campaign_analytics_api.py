"""
ACL layer for core/campaign_analytics.py (A/B Testing + Revenue Tracking) and
core/email_personalization.py (Dynamic Personalization) -- imported directly
into api/app.py's route handlers, same "no service layer indirection"
convention every other `*_api.py` module in this codebase follows.

Role rule: viewing a campaign's revenue/A-B results follows
core/campaigns_api.py's own `get_campaign_api` rule exactly -- the campaign's
creator, or MARKETING/ADMIN. Setting up an A/B variant matches
core/campaigns_api.py's `_can_activate` (MARKETING/ADMIN) -- a campaign-
configuration action, same power level as activating one. Personalization
preview matches core/email_templates_api.py's own `_can_access` (a template's
creator, or MARKETING/ADMIN) -- previewing how a template renders for a real
recipient is part of editing that template.
"""

from core.permissions import ADMIN, MARKETING
from core.campaigns import get_campaign
from core.email_templates import get_template
from core.campaign_analytics import (
    set_ab_variant,
    clear_ab_variant,
    get_campaign_ab_config,
    get_ab_test_results,
    get_campaign_revenue,
)
from core.email_personalization import list_merge_fields, get_merge_values, render_personalized


def _can_manage_all(role):
    return role == ADMIN or role == MARKETING


def _can_view_campaign(role, employee_id, campaign):
    return _can_manage_all(role) or campaign.attributes.get("created_by") == employee_id


def _can_access_template(role, employee_id, template):
    return _can_manage_all(role) or template.attributes.get("created_by") == employee_id


def set_ab_variant_api(role, campaign_id, variant_b_template_id):
    if not _can_manage_all(role):
        return {"error": "You don't have access to configure A/B tests"}
    return set_ab_variant(campaign_id, variant_b_template_id)


def clear_ab_variant_api(role, campaign_id):
    if not _can_manage_all(role):
        return {"error": "You don't have access to configure A/B tests"}
    return clear_ab_variant(campaign_id)


def get_campaign_ab_config_api(role, employee_id, campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    if not _can_view_campaign(role, employee_id, campaign):
        return {"error": "You don't have access to this campaign"}
    return get_campaign_ab_config(campaign_id)


def get_ab_test_results_api(role, employee_id, campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    if not _can_view_campaign(role, employee_id, campaign):
        return {"error": "You don't have access to this campaign"}
    return get_ab_test_results(campaign_id)


def get_campaign_revenue_api(role, employee_id, campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    if not _can_view_campaign(role, employee_id, campaign):
        return {"error": "You don't have access to this campaign"}
    return get_campaign_revenue(campaign_id)


def list_merge_fields_api():
    return list_merge_fields()


def get_merge_values_api(role, employee_id, person_id):
    return get_merge_values(person_id)


def render_personalized_api(role, employee_id, template_id, person_id):
    template = get_template(template_id)
    if not template:
        return {"error": "Template not found"}
    if not _can_access_template(role, employee_id, template):
        return {"error": "You don't have access to this template"}
    return render_personalized(template_id, person_id)
