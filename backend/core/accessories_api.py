"""Thin ACL layer for core/accessories.py's graph-native Accessories
Accelerator -- same "no service-layer indirection" convention as every other
*_api.py module in this codebase.

VIEW_ROLES is (ADMIN, OPERATIONS, SALES, MARKETING): accessories are a
sales-and-marketing motion -- Sales attaches them at the point of delivery,
Marketing runs the campaigns/pitches around them, and ADMIN/OPERATIONS get the
same GM-level oversight of the whole store they get everywhere else. SERVICE and
FINANCE are excluded here (unlike the broader six-role Communications Hub /
Customer Journey views) because accessory upsell/attach is not a service-lane or
F&I concern -- narrower on purpose, matching the DASHBOARD_ACCESS "sales" tier
(ADMIN/OPERATIONS/SALES/MARKETING) rather than the full six-role tier.

core/accessories.py raises ValueError on an unknown customer / invalid category
/ unknown item / already-installed sale; this layer catches that and returns the
same {"error": ...} dict shape every other *_api.py module surfaces, so routers
and callers get one uniform error contract.
"""

from core.accessories import (
    create_accessory_sale,
    generate_accessory_pitch,
    get_accessories_overview,
    list_accessory_catalog,
    mark_installed,
    recommend_accessories,
)

VIEW_ROLES = ("ADMIN", "OPERATIONS", "SALES", "MARKETING")


def list_accessory_catalog_api(role, category=None):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the accessory catalog."}

    try:
        return list_accessory_catalog(category=category)
    except ValueError as exc:
        return {"error": str(exc)}


def get_accessories_overview_api(role):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view the accessories overview."}

    return get_accessories_overview()


def recommend_accessories_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to view accessory recommendations."}

    try:
        return recommend_accessories(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}


def create_accessory_sale_api(role, customer_id, item_ids):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to record an accessory sale."}

    try:
        return create_accessory_sale(customer_id, item_ids)
    except ValueError as exc:
        return {"error": str(exc)}


def mark_installed_api(role, customer_id, sale_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to mark an accessory install."}

    try:
        return mark_installed(customer_id, sale_id)
    except ValueError as exc:
        return {"error": str(exc)}


def generate_accessory_pitch_api(role, customer_id):

    if role not in VIEW_ROLES:
        return {"error": f"Role '{role}' is not permitted to generate an accessory pitch."}

    try:
        return generate_accessory_pitch(customer_id)
    except ValueError as exc:
        return {"error": str(exc)}
