"""
Thin API-layer functions for the website/inventory builder (session 32; rebuilt into a
real product session 58 -- setup wizard, DealerGPT mode, canvas locking, admin
DNS/SEO/bot/analytics/OEM-branding controls), imported directly into api/app.py's route
handlers -- same "no service layer indirection" convention every other `*_api.py`
module in this codebase follows. ACL checks live here (not in core/websites.py),
mirroring core/assets_api.py/core/campaigns_api.py.

Role rule, matching the precedent Sam already approved twice (assets session 30,
campaigns session 31) and extended session 58: any authenticated role can create a
draft site (via the wizard or blank), add/remove/lock sections, and submit it, as long
as they're the site's original builder or one of its `owners` (or ADMIN); only
MARKETING or ADMIN can approve (publish) or reject a site, see the pending-approval
queue, or change its admin_settings (DNS/SEO/bot/analytics/branding) -- Sam's "from the
admin side they can control..." framing draws that line explicitly. Removing or
re-locking an already-`locked` section always requires MARKETING/ADMIN regardless of
ownership, even mid-draft -- that's the whole point of locking a section.
"""

from core.website_revisions import has_public_version
from core.websites import (
    list_section_templates,
    get_section_template,
    list_page_keys,
    list_modes,
    create_website,
    create_website_from_wizard,
    get_website,
    add_section,
    update_section_fields,
    remove_section,
    set_section_locked,
    set_mode,
    add_owner,
    remove_owner,
    update_admin_settings,
    get_dns_instructions,
    get_robots_txt,
    get_website_rendered,
    submit_for_approval,
    approve_website,
    reject_website,
    list_websites,
    list_pending_approvals,
    is_owner,
    PAGE_KEYS,
    list_site_templates,
    get_site_template,
    apply_site_template,
    reorder_sections,
    set_page_layout_mode,
    set_section_layout,
    add_library_image,
    remove_library_image,
    list_library_images,
    regenerate_section,
    update_page_seo,
    get_page_seo,
    submit_contact_form,
    record_page_view,
    get_website_analytics,
    get_vehicle_landing_page,
    generate_vehicle_page_description,
    add_personalization_variant,
    remove_personalization_variant,
    list_personalization_variants,
)
from core.website_seo import get_sitemap_xml, get_seo_health, get_structured_data
from core.website_wizard import generate_page_seo_copy, fallback_seo_copy
from core.permissions import ADMIN, MARKETING
from core.audit import audit_log
from core.audit_storage import save_audit_log
from core.storage_paths import AUDIT_PATH
from core.compliance import enforce_gate
from core.website_revisions import serialized_website_write, review_is_current


def _serialize_website(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def _can_review(role):
    return role == ADMIN or role == MARKETING


def _can_edit_content(role, employee_id, website):
    """Builder-level access: the original requester, any current owner, or ADMIN."""

    return (
        role == ADMIN
        or website.attributes.get("requested_by") == employee_id
        or is_owner(website, employee_id)
    )


def list_section_templates_api():
    return list_section_templates()


def list_page_keys_api():
    return list_page_keys()


def list_modes_api():
    return list_modes()


def create_website_api(employee_id, name, mode="traditional"):

    if not (name or "").strip():
        return {"error": "A site name is required"}

    entity = create_website(name.strip(), employee_id, mode=mode)

    return _serialize_website(entity)


def create_website_wizard_api(employee_id, dealership_info, mode="traditional"):
    """Sam: 'have dealerOS create the website through a setup wizard... let ai write
    the content and set it up.' Any authenticated role can run the wizard (same as
    starting a blank draft) -- it still lands in 'draft' status and still needs
    MARKETING/ADMIN approval to publish, same gate as every other path to a site."""

    if not (dealership_info or {}).get("dealership_name"):
        return {"error": "A dealership name is required"}

    entity = create_website_from_wizard(dealership_info, employee_id, mode=mode)

    return _serialize_website(entity)


def add_section_api(role, employee_id, website_id, page_key, section_key, fields):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = add_section(website_id, page_key, section_key, fields, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def update_section_fields_api(role, employee_id, website_id, page_key, section_index, fields):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = update_section_fields(website_id, page_key, section_index, fields, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def remove_section_api(role, employee_id, website_id, page_key, section_index):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    try:
        pages = website.attributes.get("pages") or {}
        target = (pages.get(page_key) or {}).get("sections", [])[section_index]
    except (IndexError, TypeError):
        target = None

    if target and target.get("locked") and not _can_review(role):
        return {"error": "This section is locked -- only MARKETING/ADMIN can remove a locked section"}

    result = remove_section(website_id, page_key, section_index, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def set_section_locked_api(role, employee_id, website_id, page_key, section_index, locked):
    """Sam: 'we can lock stuff if we feel they'll mess it up' -- locking/unlocking is
    itself a MARKETING/ADMIN-only action, not something a regular builder/owner can do
    to their own site (otherwise locking would be meaningless)."""

    if not _can_review(role):
        return {"error": "Only MARKETING/ADMIN can lock or unlock a section"}

    result = set_section_locked(website_id, page_key, section_index, locked, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def set_mode_api(role, employee_id, website_id, mode):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't change mode in that state"}

    result = set_mode(website_id, mode, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def add_owner_api(role, employee_id, website_id, new_owner_employee_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_review(role) and not _can_edit_content(role, employee_id, website):
        return {"error": "You don't have access to manage this site's owners"}

    result = add_owner(website_id, new_owner_employee_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def remove_owner_api(role, employee_id, website_id, owner_employee_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_review(role) and not _can_edit_content(role, employee_id, website):
        return {"error": "You don't have access to manage this site's owners"}

    result = remove_owner(website_id, owner_employee_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def update_admin_settings_api(role, employee_id, website_id, patch):
    """Sam: 'from the admin side they can control the DNS info... SEO, Bot stuff... "
    Google / umami style analytics... facebook ads codes... code snippits' -- and OEM
    vs. independent branding. All of it gated to MARKETING/ADMIN, matching the same
    line Sam already drew for approve/reject/pending-queue access."""

    if not _can_review(role):
        return {"error": "Only MARKETING/ADMIN can change this site's admin settings"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    result = update_admin_settings(website_id, patch, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def get_dns_instructions_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_dns_instructions(website_id)


def get_robots_txt_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_robots_txt(website_id)


@serialized_website_write
def submit_website_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can submit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is already '{website.attributes.get('status')}', not a draft"}

    updated = submit_for_approval(website_id, by=employee_id)
    if isinstance(updated, dict) and "error" in updated:
        return updated

    return _serialize_website(updated)


def get_website_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    rendered = get_website_rendered(website_id)

    return rendered


def list_my_websites_api(employee_id):
    return [_serialize_website(w) for w in list_websites(created_by=employee_id)]


def list_pending_websites_api(role):

    if not _can_review(role):
        return {"error": "You don't have access to the website approval queue"}

    return [_serialize_website(w) for w in list_pending_approvals()]


@serialized_website_write
def approve_website_api(role, reviewer_id, website_id, notes=None):

    if not _can_review(role):
        return {"error": "You don't have access to publish sites"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if website.attributes.get("status") != "pending_approval":
        return {"error": f"Site is '{website.attributes.get('status')}', not pending approval"}

    if website.attributes.get("studio_config") and not review_is_current(website):
        return {"error": "The submitted website changed. Reject it and request a fresh review before publishing."}

    # Compliance agent (session 38) -- advertising disclosure check runs on every
    # public-facing website before it publishes.
    gate = enforce_gate("website_publish", website)

    if gate["blocked"]:
        return {
            "error": "Compliance check failed -- this site can't publish until the issue(s) below are corrected.",
            "compliance_alert_id": gate["alert_id"],
            "compliance_violations": gate["violations"],
            "notice": gate["notice"],
        }

    updated = approve_website(website_id, reviewer_id, notes)
    if isinstance(updated, dict) and "error" in updated:
        return updated

    audit_log.record(
        event_type="website_published",
        summary=f"Website {website_id} published by {reviewer_id}",
        entity_id=website_id,
        actor=reviewer_id,
        details={"name": updated.attributes.get("name")},
    )
    save_audit_log(AUDIT_PATH)

    return _serialize_website(updated)


def list_site_templates_api(dealer_type=None):
    """Layout template catalog (session 85) -- open to any role, same as
    list_section_templates_api, since browsing templates is just reading a fixed
    catalog, not touching a specific site."""

    return list_site_templates(dealer_type)


def apply_site_template_api(role, employee_id, website_id, template_key, dealership_name=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = apply_site_template(website_id, template_key, dealership_name=dealership_name, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def reorder_sections_api(role, employee_id, website_id, page_key, new_order):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = reorder_sections(website_id, page_key, new_order, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


# Website Personalization (2026-07-19) -- same ACL shape as every other builder-content
# mutation above: this site's own builder/owners or an ADMIN, only while the site is
# still "draft"/"rejected" (a variant is authoring content, same gate add_section_api/
# update_section_fields_api already enforce). Viewing a section's variants is read-only
# and uses the same builder-or-reviewer access line as get_website_analytics_api.
def add_personalization_variant_api(role, employee_id, website_id, page_key, section_index, match, field_overrides):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = add_personalization_variant(website_id, page_key, section_index, match, field_overrides, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def remove_personalization_variant_api(role, employee_id, website_id, page_key, section_index, variant_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = remove_personalization_variant(website_id, page_key, section_index, variant_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def list_personalization_variants_api(role, employee_id, website_id, page_key, section_index):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return list_personalization_variants(website_id, page_key, section_index)


# Freeform drag-and-drop canvas (2026-07-18) -- same ACL shape as every other
# builder-content mutation above (reorder/add/remove/edit): only this site's own
# builder/owners or an ADMIN, and only while the site is still in "draft"/"rejected".
def set_page_layout_mode_api(role, employee_id, website_id, page_key, mode):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = set_page_layout_mode(website_id, page_key, mode, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def set_section_layout_api(role, employee_id, website_id, page_key, section_index, x, y, width, height):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = set_section_layout(website_id, page_key, section_index, x, y, width, height, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def regenerate_section_api(role, employee_id, website_id, page_key, section_index, instructions=None):
    """Per-section 'AI writing abilities' (session 85) -- same builder/owner/admin +
    draft-or-rejected gate as editing any other section content."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    if website.attributes.get("status") not in ("draft", "rejected"):
        return {"error": f"Site is '{website.attributes.get('status')}' -- can't edit it in that state"}

    result = regenerate_section(website_id, page_key, section_index, instructions=instructions, by=employee_id)

    if isinstance(result, dict) and "error" in result and "website" not in result:
        return result

    if isinstance(result, dict) and "error" in result:
        return {"error": result["error"], **_serialize_website(result["website"])}

    return _serialize_website(result)


def add_library_image_api(role, employee_id, website_id, url, label=None):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    result = add_library_image(website_id, url, label=label, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def remove_library_image_api(role, employee_id, website_id, image_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website):
        return {"error": "Only this site's builder/owners (or an admin) can edit it"}

    result = remove_library_image(website_id, image_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def list_library_images_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return list_library_images(website_id)


def update_page_seo_api(role, employee_id, website_id, page_key, patch):
    """Per-page SEO (session 85) -- same MARKETING/ADMIN-only line Sam already drew for
    the rest of admin_settings (DNS/bot/analytics/branding)."""

    if not _can_review(role):
        return {"error": "Only MARKETING/ADMIN can change this site's SEO settings"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    result = update_page_seo(website_id, page_key, patch, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_website(result)


def get_page_seo_api(role, employee_id, website_id, page_key):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_page_seo(website_id, page_key)


# --- Enterprise SEO automation (session 113 follow-up) -----------------------------
# Same view-access line as DNS/robots.txt above (builder-level OR MARKETING/ADMIN);
# generating AI meta copy stays MARKETING/ADMIN-only, matching update_page_seo_api's
# own "SEO settings are a marketing decision" rule exactly.

def get_sitemap_xml_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_sitemap_xml(website_id)


def get_seo_health_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_seo_health(website_id)


def get_structured_data_api(role, employee_id, website_id):

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    return get_structured_data(website_id)


def _page_content_summary(website, page_key):
    """A plain-text grounding summary of a page's real content -- every text-typed
    field value across every section on the page, joined -- so the AI meta-copy call
    is drafting from what the page actually says, not guessing."""

    page = (website.attributes.get("pages") or {}).get(page_key) or {}
    parts = []

    for section in page.get("sections") or []:
        for value in (section.get("fields") or {}).values():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

    return " ".join(parts)[:600] or None


def generate_page_seo_copy_api(role, employee_id, website_id, page_key):
    """AI-drafts a meta title/description grounded in the page's own real content --
    returns the draft for the caller to review/apply via update_page_seo_api(), same
    'draft, don't auto-apply' precedent core/website_wizard.py's other functions
    already follow (unlike core/reputation.py's auto-respond bot)."""

    if not _can_review(role):
        return {"error": "Only MARKETING/ADMIN can generate SEO copy for this site"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if page_key not in PAGE_KEYS:
        return {"error": f"Unknown page '{page_key}'"}

    summary = _page_content_summary(website, page_key)

    result = generate_page_seo_copy(website.attributes.get("name"), page_key, summary)

    if "error" in result:
        return {**fallback_seo_copy(website.attributes.get("name"), page_key), "ai_generated": False}

    return {**result, "ai_generated": True}


def regenerate_vehicle_description_api(role, employee_id, website_id, vehicle_id):
    """AI-regenerates (and caches) a Vehicle Detail Page's description -- same
    MARKETING/ADMIN-only gate as generate_page_seo_copy_api(), since this is a
    builder-side authoring action, not something a real site visitor triggers (the
    public VDP route below just reads whatever's already cached)."""

    if not _can_review(role):
        return {"error": "Only MARKETING/ADMIN can regenerate a vehicle's description"}

    return generate_vehicle_page_description(website_id, vehicle_id, by=employee_id)


def preview_website_api(role, employee_id, website_id, mode_override=None, utm_source=None, referrer=None):
    """Authenticated 'preview the site' action for the builder itself (Sam: 'preview
    the site' under the admin section) -- distinct from the public, unauthenticated
    render path (see get_public_website_api below), but reuses the exact same
    get_website_rendered()/mode_override mechanism and also logs a real page-view
    event, since a builder previewing their own site is genuine traffic too.
    `utm_source`/`referrer` (2026-07-19) let a builder test their own Personalization
    Variants before publishing, by simulating the visitor signal a variant matches on."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    record_page_view(website_id, "preview", viewer_ref=employee_id)

    return get_website_rendered(website_id, mode_override=mode_override, utm_source=utm_source, referrer=referrer)


def get_website_analytics_api(role, employee_id, website_id, days=30):
    """The Google-Analytics/Umami-style admin reporting Sam asked for -- same access
    line as DNS/robots.txt (builder/owner/admin or MARKETING/ADMIN reviewer)."""

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if not _can_edit_content(role, employee_id, website) and not _can_review(role):
        return {"error": "You don't have access to this site"}

    from core.website_visits import report
    return {**get_website_analytics(website_id), "traffic": report(website_id, days)}


def get_public_website_api(website_id, mode_override=None, user_agent=None, utm_source=None, referrer=None):
    """The real, PUBLIC-facing render path (session 85) -- no role/employee_id, no
    Authorization header at all, since an actual dealership website visitor is an
    anonymous customer, not a logged-in NXTDeal employee. Only ever serves a
    'published' site; drafts/pending/rejected sites 404 here even though they're fully
    visible to their builder/owner via the authenticated preview_website_api above --
    an unpublished draft should never be reachable by an anonymous visitor. Every real
    hit here logs a real WebsiteAnalyticsEvent (record_page_view()), backing the
    Google-Analytics/Umami-style admin reporting with genuine (if sandboxed) traffic.
    `user_agent` (session 86) is the real request's User-Agent header, threaded through
    from api/app.py, backing the real bot-vs-human traffic classification.
    `utm_source`/`referrer` (2026-07-19, Website Personalization) are the real
    `?utm_source=` query param and the real `Referer` request header a live visitor's
    browser sends -- both threaded straight through to get_website_rendered() so each
    section's own personalization_variants overlay actually has something real to
    match against on a genuine visit, not just an authenticated preview."""

    website = get_website(website_id)

    if not has_public_version(website):
        return {"error": "Site not found"}

    record_page_view(website_id, "home", viewer_ref=None, user_agent=user_agent)

    rendered = get_website_rendered(website_id, mode_override=mode_override, utm_source=utm_source, referrer=referrer, published=True)
    # Internal approval records and employee identities are not public content.
    for key in ("review_snapshot", "published_snapshot", "review_fingerprint", "published_fingerprint", "history", "owners", "requested_by", "reviewed_by", "review_notes", "image_library", "vehicle_pages", "studio_creation_key"):
        rendered.pop(key, None)
    return rendered


def submit_contact_form_api(website_id, page_key, section_index, name, email=None, phone=None, message=None, vehicle_id=None, intent=None, request_id=None):
    """PUBLIC contact-form submission (session 85) -- Sam: 'contact forms that feed
    into the crm.' No auth: an anonymous site visitor submits this. Only accepted on a
    'published' site, same reasoning as get_public_website_api above."""

    website = get_website(website_id)

    if not has_public_version(website):
        return {"error": "Site not found"}

    return submit_contact_form(website_id, page_key, section_index, name, email=email, phone=phone, message=message, vehicle_id=vehicle_id, intent=intent, request_id=request_id)


def reject_website_api(role, reviewer_id, website_id, notes=None):

    if not _can_review(role):
        return {"error": "You don't have access to reject sites"}

    website = get_website(website_id)

    if not website:
        return {"error": "Website not found"}

    if website.attributes.get("status") != "pending_approval":
        return {"error": f"Site is '{website.attributes.get('status')}', not pending approval"}

    updated = reject_website(website_id, reviewer_id, notes)

    audit_log.record(
        event_type="website_rejected",
        summary=f"Website {website_id} rejected by {reviewer_id}",
        entity_id=website_id,
        actor=reviewer_id,
        details={"name": updated.attributes.get("name"), "notes": notes},
    )
    save_audit_log(AUDIT_PATH)

    return _serialize_website(updated)
