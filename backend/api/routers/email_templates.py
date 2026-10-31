"""Email/SMS Templates routes, extracted from api/app.py (CAF-00120,
god_file_app_py -- splitting the monolithic app.py into per-domain routers).

Graph-native, same as Campaigns/Websites: an EmailTemplate is an Entity in the
same ledger as everything else (core/email_templates.py), tied to the
Employee who built it. Any role can create/edit their own templates;
MARKETING/ADMIN can additionally see and edit every template
(core/email_templates_api.py's ACL). A template only actually sends once
it's attached to a Campaign (linked_template_id) and that Campaign is
activated -- no separate send-approval step here.

Also carries the Marketing Growth Platform's Email/SMS upgrades slice
(2026-07-18) -- Dynamic Personalization (merge fields/values/render) --
reusing core/campaign_analytics_api.py's functions of the same feature, not a
second personalization engine.

Real bug fixed during this extraction, not just a code move: app.py imported
`list_templates_api` from BOTH core.assets_api (Marketing Asset Templates,
0-arg signature) and core.email_templates_api (Email Templates listing,
3-arg `(role, employee_id, channel=None)` signature) into the SAME module
namespace. Since the email_templates_api import ran later in app.py's import
order, it silently shadowed the assets_api one -- meaning `/assets/templates`
was actually calling email_templates_api.list_templates_api() with zero
arguments, which would raise `TypeError: missing 2 required positional
arguments` at runtime. Moving this domain's own `list_templates_api` import
into this router's own separate module namespace removes the collision
entirely and restores /assets/templates to correctly calling
core.assets_api.list_templates_api() -- confirmed by grep that no other
import in app.py binds the name `list_templates_api` after this router's
import block is removed from app.py.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.email_templates_api import (
    list_block_types_api,
    list_channels_api as list_template_channels_api,
    create_template_api,
    get_template_api,
    update_template_api,
    list_my_templates_api,
    list_templates_api,
    preview_template_api,
    create_from_wizard_api,
)
from core.campaign_analytics_api import (
    list_merge_fields_api,
    get_merge_values_api,
    render_personalized_api,
)

router = APIRouter()


class CreateEmailTemplateRequest(BaseModel):

    channel: str
    name: str = None


class UpdateEmailTemplateRequest(BaseModel):

    patch: dict = {}


class EmailWizardRequest(BaseModel):

    channel: str
    goal: str = None
    audience_description: str = None
    tone: str = None


@router.get("/email-templates/design-access")
def email_templates_design_access(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.dealer_email_access import email_design_access
    return email_design_access(payload["role"], payload["employee_id"])


@router.get("/email-templates/blocks")
def email_templates_blocks(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_block_types_api()


@router.get("/email-templates/channels")
def email_templates_channels(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_template_channels_api()


@router.get("/email-templates/merge-fields")
def email_templates_merge_fields(authorization: str = Header(None)):
    """Dynamic Personalization (Marketing Growth Platform, Email/SMS upgrades
    slice) -- static path, registered here before the dynamic
    /email-templates/{template_id} path below to avoid it being shadowed."""

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_merge_fields_api()


@router.get("/email-templates/merge-values/{person_id}")
def email_templates_merge_values(person_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_merge_values_api(payload["role"], payload["employee_id"], person_id)


@router.post("/email-templates")
def email_templates_create(
    request: CreateEmailTemplateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_template_api(payload["employee_id"], request.channel, request.name)


@router.post("/email-templates/wizard")
def email_templates_wizard(
    request: EmailWizardRequest,
    authorization: str = Header(None)
):
    """Sam: 'It should have an Ai build an email wizard.' See
    core/email_wizard.py for the AI copy generation and
    core/email_templates_api.py's create_from_wizard_api() for how it's assembled
    into a full saved EmailTemplate."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_from_wizard_api(
        payload["employee_id"],
        request.channel,
        request.goal,
        request.audience_description,
        request.tone,
    )


@router.get("/email-templates/mine")
def email_templates_mine(
    channel: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_my_templates_api(payload["employee_id"], channel)


@router.get("/email-templates/all")
def email_templates_all(
    channel: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_templates_api(payload["role"], payload["employee_id"], channel)


@router.get("/email-templates/{template_id}")
def email_templates_get(
    template_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_template_api(payload["role"], payload["employee_id"], template_id)


@router.post("/email-templates/{template_id}")
def email_templates_update(
    template_id: str,
    request: UpdateEmailTemplateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_template_api(payload["role"], payload["employee_id"], template_id, request.patch)


@router.get("/email-templates/{template_id}/preview")
def email_templates_preview(
    template_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_template_api(payload["role"], payload["employee_id"], template_id)


@router.get("/email-templates/{template_id}/personalize/{person_id}")
def email_templates_personalize(
    template_id: str,
    person_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return render_personalized_api(payload["role"], payload["employee_id"], template_id, person_id)
