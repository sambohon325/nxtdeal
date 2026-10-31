"""
Thin ACL layer for core/personal_sites.py (session 85), imported directly into
api/app.py -- same "no service layer indirection" convention as every other *_api.py
module here.

Role rule: self-service. Any authenticated employee can create, edit, and
activate/deactivate their OWN personal site (site.attributes['employee_id'] must equal
the acting employee, or the acting role is ADMIN). There's no MARKETING/ADMIN approval
queue here, unlike core/websites.py's Website -- Sam's framing ('deployed by the sales
rep or marketing / events') was explicitly self-service, not something a rep drafts and
waits on marketing to publish. ADMIN can still manage/deactivate any employee's page
(e.g. an employee who's left the dealership).
"""

from core.personal_sites import (
    create_personal_site,
    get_personal_site,
    get_personal_site_by_slug,
    update_personal_site,
    set_slug,
    set_parent_website,
    set_personal_site_status,
    get_personal_site_rendered,
    record_personal_site_view,
    get_personal_site_analytics,
    submit_personal_site_contact_form,
    list_personal_sites,
    slug_available,
)
from core.permissions import ADMIN


def _serialize(entity):
    return {"id": entity.id, **entity.attributes}


def _owns(role, employee_id, site):
    return role == ADMIN or site.attributes.get("employee_id") == employee_id


def check_slug_api(slug):
    return {"slug": (slug or "").strip().lower(), "available": slug_available(slug)}


def create_personal_site_api(role, employee_id, slug, parent_website_id=None):

    result = create_personal_site(employee_id, slug, parent_website_id=parent_website_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def get_my_personal_site_api(employee_id):
    """Convenience lookup -- most employees have at most one personal page."""

    sites = list_personal_sites(employee_id=employee_id)

    return _serialize(sites[0]) if sites else None


def list_personal_sites_api(role, employee_id, mine_only=True):

    if role == ADMIN and not mine_only:
        return [_serialize(s) for s in list_personal_sites()]

    return [_serialize(s) for s in list_personal_sites(employee_id=employee_id)]


def get_personal_site_api(role, employee_id, site_id):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to this page"}

    return get_personal_site_rendered(site_id)


def update_personal_site_api(role, employee_id, site_id, patch):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to edit this page"}

    result = update_personal_site(site_id, patch, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def set_personal_site_slug_api(role, employee_id, site_id, new_slug):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to edit this page"}

    result = set_slug(site_id, new_slug, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def set_personal_site_parent_api(role, employee_id, site_id, parent_website_id):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to edit this page"}

    result = set_parent_website(site_id, parent_website_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def set_personal_site_status_api(role, employee_id, site_id, status):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to this page"}

    result = set_personal_site_status(site_id, status, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize(result)


def preview_personal_site_api(role, employee_id, site_id):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to this page"}

    # Editing previews are not customer traffic and must not inflate page views.

    return get_personal_site_rendered(site_id)


def get_personal_site_analytics_api(role, employee_id, site_id):

    site = get_personal_site(site_id)

    if not site:
        return {"error": "Personal site not found"}

    if not _owns(role, employee_id, site):
        return {"error": "You don't have access to this page"}

    return get_personal_site_analytics(site_id)


def get_public_personal_site_api(slug):
    """PUBLIC, unauthenticated -- an anonymous visitor to a rep's personal URL. Only
    ever serves an 'active' page, same 'draft/inactive never reachable publicly'
    discipline as core/websites.py's get_public_website_api."""

    site = get_personal_site_by_slug(slug)

    if not site or site.attributes.get("status") != "active":
        return {"error": "Page not found"}

    record_personal_site_view(site.id, viewer_ref=None)

    # Owner previews include edit history and internal relationship identifiers.
    # Anonymous visitors only receive explicitly published page content. Keep an
    # allowlist so future private attributes cannot silently become public.
    rendered = get_personal_site_rendered(site.id)
    public_fields = (
        "slug", "headline", "subheadline", "bio", "photo_url", "phone",
        "email", "cta_text", "calendar_link", "review_link", "featured_vehicles", "branding",
    )
    return {key: rendered.get(key) for key in public_fields}


def submit_personal_site_contact_form_api(slug, name, email=None, phone=None, message=None):
    """PUBLIC, unauthenticated contact-form submission on a rep's personal page."""

    site = get_personal_site_by_slug(slug)

    if not site:
        return {"error": "Page not found"}

    return submit_personal_site_contact_form(site.id, name, email=email, phone=phone, message=message)
