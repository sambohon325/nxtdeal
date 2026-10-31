"""
ACL layer for core/campaign_template_library.py (Bumper parity: the campaign Library).
Browsing the Library is open to any authenticated role. Saving a new template and
instantiating one into a draft campaign follow the campaign engine's own posture: creating
a draft is broad, but since a template save is a marketing-content action, template
authoring/deletion is MARKETING/ADMIN. Instantiating produces a draft (nothing sends), so
any authed role may do it.
"""

from core import campaign_template_library as lib
from core.campaigns_api import _serialize_campaign
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC

VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE, BDC)
AUTHOR_ROLES = (ADMIN, MARKETING)


def _serialize(entity):
    if isinstance(entity, dict):
        return entity
    return {"id": entity.id, **entity.attributes}


def list_template_categories_api(role):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the campaign library"}
    return {"categories": lib.list_categories()}


def list_templates_api(role, category=None, campaign_type=None, query=None):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the campaign library"}
    return {"templates": [_serialize(t) for t in lib.list_templates(category=category, campaign_type=campaign_type, query=query)]}


def get_template_api(role, template_id):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the campaign library"}
    t = lib.get_template(template_id)
    if not t:
        return {"error": "Template not found"}
    return _serialize(t)


def create_template_api(role, employee_id, name, campaign_type, channel, default_params=None,
                        category="General", description="", suggested_subject="", suggested_body="", tags=None):
    if role not in AUTHOR_ROLES:
        return {"error": "Marketing/Admin role required to save a campaign template"}
    result = lib.create_template(
        name, campaign_type, channel, employee_id, default_params=default_params, category=category,
        description=description, suggested_subject=suggested_subject, suggested_body=suggested_body, tags=tags,
    )
    if isinstance(result, dict) and result.get("error"):
        return result
    return _serialize(result)


def delete_template_api(role, employee_id, template_id):
    if role not in AUTHOR_ROLES:
        return {"error": "Marketing/Admin role required to delete a campaign template"}
    return lib.delete_template(template_id)


def instantiate_template_api(role, employee_id, template_id, name_override=None, params_override=None, channel_override=None):
    if role not in VIEW_ROLES:
        return {"error": "You don't have access to the campaign library"}
    result = lib.instantiate_template(
        template_id, employee_id, name_override=name_override,
        params_override=params_override, channel_override=channel_override,
    )
    if isinstance(result, dict) and result.get("error"):
        return result
    return _serialize_campaign(result)
