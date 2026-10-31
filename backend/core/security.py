from core.administration_access import SYSTEM_ENTITY_TYPES, system_admin_context
from core.permissions import ADMIN, ENTITY_ACCESS, DASHBOARD_ACCESS
from core.entity_types import API_KEY


def can_access_entity(
    role,
    entity_type
):
    """Except internal API-key records, ADMIN passes regardless of entity_type â€” including entity types not yet
    listed in ENTITY_ACCESS (e.g. Employee, Campaign, Vendor exist in core/entity_types.py
    but have no ENTITY_ACCESS entry today; without this bypass even ADMIN would be denied
    for those via the empty-list default below). Non-admin roles are checked against
    ENTITY_ACCESS as before."""

    # Raw key records contain verifier/binding material, not business data.
    # Use the dedicated key endpoints, which serialize only safe metadata.
    if entity_type == API_KEY:
        return False

    if entity_type in SYSTEM_ENTITY_TYPES and not system_admin_context.get():
        return False

    if role == ADMIN:

        return True

    allowed_roles = ENTITY_ACCESS.get(
        entity_type,
        []
    )

    return role in allowed_roles


def can_access_dashboard(
    role,
    dashboard_key
):
    """Same ADMIN-always-passes shape as can_access_entity, checked against
    core/permissions.py's DASHBOARD_ACCESS instead of ENTITY_ACCESS. See that dict's
    comment for where these per-department assumptions came from."""

    if dashboard_key in ("audit", "success_center") and not system_admin_context.get():
        return False

    if role == ADMIN:

        return True

    allowed_roles = DASHBOARD_ACCESS.get(
        dashboard_key,
        []
    )

    return role in allowed_roles
