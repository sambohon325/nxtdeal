"""Personal URL microsites routes, extracted from api/app.py (CAF-00120,
god_file_app_py -- splitting the monolithic app.py into per-domain routers).

Session 85 -- Website Builder overhaul (personal URL microsites + live chat
wired into the CRM). See core/personal_sites.py's own module docstring for
the scoping decision made autonomously after an AskUserQuestion tool failure:
a PersonalSite is a single-page personal landing page per employee, not a
full site mirror.

Includes both the authenticated builder-side routes (/personal-sites/*) and
the two genuinely public, unauthenticated visitor-facing routes
(/public/personal-sites/{slug}[/contact]) -- a lead captured via the contact
form is assigned directly to the page's owning employee, the real "deployed
by the sales rep... feeds into the CRM" tie.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.personal_sites_api import (
    check_slug_api,
    create_personal_site_api,
    get_my_personal_site_api,
    list_personal_sites_api,
    get_personal_site_api,
    update_personal_site_api,
    set_personal_site_slug_api,
    set_personal_site_parent_api,
    set_personal_site_status_api,
    preview_personal_site_api,
    get_personal_site_analytics_api,
    get_public_personal_site_api,
    submit_personal_site_contact_form_api,
)

router = APIRouter()


class CreatePersonalSiteRequest(BaseModel):

    slug: str
    parent_website_id: str | None = None


class UpdatePersonalSiteRequest(BaseModel):

    patch: dict


class SetPersonalSiteSlugRequest(BaseModel):

    slug: str


class SetPersonalSiteParentRequest(BaseModel):

    parent_website_id: str | None = None


class SetPersonalSiteStatusRequest(BaseModel):

    status: str


class SubmitPersonalSiteContactFormRequest(BaseModel):

    name: str
    email: str = None
    phone: str = None
    message: str = None


@router.get("/personal-sites/check-slug")
def personal_sites_check_slug(slug: str, authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return check_slug_api(slug)


@router.post("/personal-sites")
def personal_sites_create(request: CreatePersonalSiteRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_personal_site_api(payload["role"], payload["employee_id"], request.slug, request.parent_website_id)


@router.get("/personal-sites/mine")
def personal_sites_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_my_personal_site_api(payload["employee_id"])


@router.get("/personal-sites")
def personal_sites_list(mine_only: bool = True, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_personal_sites_api(payload["role"], payload["employee_id"], mine_only)


@router.get("/personal-sites/{site_id}")
def personal_sites_get(site_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_personal_site_api(payload["role"], payload["employee_id"], site_id)


@router.post("/personal-sites/{site_id}")
def personal_sites_update(site_id: str, request: UpdatePersonalSiteRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_personal_site_api(payload["role"], payload["employee_id"], site_id, request.patch)


@router.post("/personal-sites/{site_id}/slug")
def personal_sites_set_slug(site_id: str, request: SetPersonalSiteSlugRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_personal_site_slug_api(payload["role"], payload["employee_id"], site_id, request.slug)


@router.post("/personal-sites/{site_id}/parent")
def personal_sites_set_parent(site_id: str, request: SetPersonalSiteParentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_personal_site_parent_api(payload["role"], payload["employee_id"], site_id, request.parent_website_id)


@router.post("/personal-sites/{site_id}/status")
def personal_sites_set_status(site_id: str, request: SetPersonalSiteStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_personal_site_status_api(payload["role"], payload["employee_id"], site_id, request.status)


@router.get("/personal-sites/{site_id}/preview")
def personal_sites_preview(site_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_personal_site_api(payload["role"], payload["employee_id"], site_id)


@router.get("/personal-sites/{site_id}/analytics")
def personal_sites_analytics(site_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_personal_site_analytics_api(payload["role"], payload["employee_id"], site_id)


@router.get("/public/personal-sites/{slug}")
def public_personal_site_get(slug: str):
    """PUBLIC, unauthenticated -- an anonymous visitor to a rep's personal URL."""

    return get_public_personal_site_api(slug)


@router.post("/public/personal-sites/{slug}/contact")
def public_personal_site_contact(slug: str, request: SubmitPersonalSiteContactFormRequest):
    """PUBLIC -- a lead captured here is assigned directly to the page's owning
    employee, the actual 'deployed by the sales rep... feeds into the CRM' tie."""

    return submit_personal_site_contact_form_api(slug, request.name, request.email, request.phone, request.message)
