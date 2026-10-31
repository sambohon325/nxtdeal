from core.permissions import ENTITY_ACCESS
from core.administration_access import SYSTEM_ENTITY_TYPES, system_admin_context


def get_visible_entities(role):

    visible = []

    for entity_type, roles in ENTITY_ACCESS.items():

        if role in roles:

            if entity_type in SYSTEM_ENTITY_TYPES and not system_admin_context.get():
                continue

            visible.append(entity_type)

    return visible