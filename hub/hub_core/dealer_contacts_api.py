"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/dealer_contacts.py.
"""

from hub_core.dealer_contacts import (
    CONTACT_ROLES,
    CONTACT_ROLE_LABELS,
    add_contact,
    remove_contact,
    get_dealer_users,
)
from hub_core.dealer_contacts_storage import save_dealer_contacts
from hub_core.hub_audit_api import record_and_save

DEALER_CONTACTS_PATH = "storage/dealer_contacts.json"


def get_users_catalog_api():
    return {
        "roles": [
            {"key": key, "label": CONTACT_ROLE_LABELS[key]} for key in CONTACT_ROLES
        ],
    }


def get_dealer_users_api(dealer_id):
    result, error = get_dealer_users(dealer_id)
    if error:
        return {"error": error}
    return result


def add_dealer_contact_api(dealer_id, name, role, email=None, phone=None, added_by="nxtdeal_staff"):

    contact, error = add_contact(dealer_id, name, role, email=email, phone=phone, added_by=added_by)
    if error:
        return {"error": error}

    save_dealer_contacts(DEALER_CONTACTS_PATH)

    record_and_save(
        event_type="dealer_contact_added",
        summary=f"Contact '{contact.name}' ({role}) added for {dealer_id} by {added_by}",
        dealer_id=dealer_id,
        actor=added_by,
        details={"contact_id": contact.contact_id, "role": role},
    )

    result, _ = get_dealer_users(dealer_id)
    return result


def remove_dealer_contact_api(contact_id, removed_by="nxtdeal_staff"):

    contact, error = remove_contact(contact_id)
    if error:
        return {"error": error}

    save_dealer_contacts(DEALER_CONTACTS_PATH)

    record_and_save(
        event_type="dealer_contact_removed",
        summary=f"Contact '{contact.name}' removed from {contact.dealer_id} by {removed_by}",
        dealer_id=contact.dealer_id,
        actor=removed_by,
        details={"contact_id": contact_id},
    )

    result, _ = get_dealer_users(contact.dealer_id)
    return result
