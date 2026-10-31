"""
Graph-native Communications (2026-07-13, session 28 -- Sam: "communications will work
off the same graph knowledge (so the communication is tied to the employee, it doesn't
live in the same world)"). Channels and messages are ordinary Entity records in the same
core/dealeros.ledger every other entity type lives in -- saved/loaded automatically by
core/storage.py's save_graph()/load_graph() (already generic across entity types), no new
parallel store. This mirrors the "One Graph Unification" precedent (core/pipeline_state.py,
core/lead_assignment.py) rather than reintroducing a second disconnected data model, which
is exactly the mistake that unification fixed.

Channels are a fixed set tied to department/role (Sam's explicit scoping answer,
2026-07-13 session 28: "fixed department channels + free DMs" over fully dynamic
channel creation) -- #sales, #service, #managers, matching the three channel chips the
UI has shown since session 15. Membership is role-based (core/permissions.py's role
constants), not a stored relationship, since it should always reflect an employee's
*current* role rather than a stale invite list -- same reasoning DASHBOARD_ACCESS/
ENTITY_ACCESS already use for entity/dashboard visibility.

Direct messages are unrestricted -- any employee can message any other employee;
there's no equivalent to channel membership to gate on. Only the two participants can
ever read a given DM thread (enforced in core/messaging_api.py, not here).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CHANNEL, MESSAGE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.entity_mentions import link_entity_mentions
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This is the 15th confirmed instance and arguably the most severe: this module had
# ZERO real save_graph() calls anywhere since it shipped (session 28) -- the module
# docstring's own line 6 mentions "save_graph()" only as prose describing
# core/storage.py's general mechanism, which is exactly why the earlier grep-based
# sweep for this bug class missed it (a docstring substring match, not an actual
# import/call). Every real channel message and direct message ever sent through the
# live app -- the entire Communications system backing /ws/messaging and
# components/ChatDock.tsx -- had been silently discarded on server restart. Fixed
# below: both real mutating functions now save directly (human typing in chat is
# naturally rate-limited, same reasoning core/website_chat.py's fix already used, so
# no batching/conditional-save pattern is needed here).


# Fixed department channels. `roles` mirrors the same "who works this part of the
# business" reasoning core/permissions.py's DASHBOARD_ACCESS comment lays out --
# ADMIN is added automatically everywhere by can_access_channel() below, matching
# can_access_dashboard/can_access_entity's ADMIN-always-passes rule, so it's left out
# of these lists on purpose.
CHANNEL_DEFS = {
    "sales": {
        "key": "sales",
        "id": "CHAN-SALES",
        "name": "sales",
        "roles": [OPERATIONS, SALES, MARKETING],
    },
    "service": {
        "key": "service",
        "id": "CHAN-SERVICE",
        "name": "service",
        "roles": [OPERATIONS, SERVICE],
    },
    "managers": {
        "key": "managers",
        "id": "CHAN-MANAGERS",
        "name": "managers",
        "roles": [OPERATIONS, SALES, SERVICE, FINANCE, MARKETING],
    },
}


def seed_channels():
    """Idempotent -- safe to call on every process start (see api/app.py). Only ever
    creates the fixed CHANNEL_DEFS entities if they don't already exist in the loaded
    graph; never overwrites one that's already there (e.g. loaded from storage/graph.json)."""

    for key, definition in CHANNEL_DEFS.items():

        if ledger.get_entity(definition["id"]):
            continue

        ledger.add_entity(
            Entity(
                id=definition["id"],
                entity_type=CHANNEL,
                attributes={
                    "key": key,
                    "name": definition["name"],
                    "roles": definition["roles"],
                },
            )
        )


def list_channels_for_role(role):
    """Every channel a role can see -- ADMIN sees all three, everyone else sees the
    channels their role is listed under in CHANNEL_DEFS."""

    return [
        definition
        for key, definition in CHANNEL_DEFS.items()
        if role == ADMIN or role in definition["roles"]
    ]


def can_access_channel(role, channel_key):

    definition = CHANNEL_DEFS.get(channel_key)

    if not definition:
        return False

    return role == ADMIN or role in definition["roles"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_messages():
    return [
        entity
        for entity in ledger.get_all().values()
        if entity.entity_type == MESSAGE
    ]


def send_channel_message(channel_key, sender_id, content, attached_pin=None):

    message_id = id_generator.generate("MSG")

    entity = Entity(
        id=message_id,
        entity_type=MESSAGE,
        attributes={
            "kind": "channel",
            "channel_key": channel_key,
            "sender_id": sender_id,
            "content": content,
            "attached_pin": attached_pin,
            "timestamp": _now(),
        },
    )

    ledger.add_entity(entity)

    # Session 76 fourth follow-up -- a real MENTIONS relationship for every entity ID
    # referenced in the message text (see core/entity_mentions.py), so a Customer/
    # Vehicle/Deal/etc. mentioned in chat becomes explorable in reverse -- not just a
    # clickable link on the message itself.
    link_entity_mentions(message_id, content, created_by=sender_id)

    save_graph(GRAPH_PATH)

    return entity


def get_channel_messages(channel_key, limit=100):

    messages = [
        entity
        for entity in _all_messages()
        if entity.attributes.get("kind") == "channel"
        and entity.attributes.get("channel_key") == channel_key
    ]

    messages.sort(key=lambda entity: entity.attributes.get("timestamp", ""))

    return messages[-limit:]


def send_direct_message(sender_id, recipient_id, content, attached_pin=None, _skip_save=False):

    message_id = id_generator.generate("MSG")

    entity = Entity(
        id=message_id,
        entity_type=MESSAGE,
        attributes={
            "kind": "direct",
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "content": content,
            "attached_pin": attached_pin,
            "timestamp": _now(),
        },
    )

    ledger.add_entity(entity)

    # Session 76 fourth follow-up -- see send_channel_message's comment above.
    link_entity_mentions(message_id, content, created_by=sender_id)

    # _skip_save (added for core/workflow_automation.py's evaluate_rules(), which
    # can send one DM per matched entity in a single pass) -- same batching
    # precedent as create_task()'s own _skip_save above. Every other existing
    # caller is unaffected (default False, saves immediately as it always has).
    if not _skip_save:
        save_graph(GRAPH_PATH)

    return entity


def get_direct_messages(employee_a, employee_b, limit=100):

    parties = {employee_a, employee_b}

    messages = [
        entity
        for entity in _all_messages()
        if entity.attributes.get("kind") == "direct"
        and {
            entity.attributes.get("sender_id"),
            entity.attributes.get("recipient_id"),
        }
        == parties
    ]

    messages.sort(key=lambda entity: entity.attributes.get("timestamp", ""))

    return messages[-limit:]


def list_recent_conversations(employee_id):
    """Distinct DM partners for `employee_id`, most-recently-active first -- backs the
    "Direct Messages" list in the Communications sidebar (previously the static
    "Sarah"/"John" chips)."""

    latest_by_partner = {}

    for entity in _all_messages():

        if entity.attributes.get("kind") != "direct":
            continue

        sender = entity.attributes.get("sender_id")
        recipient = entity.attributes.get("recipient_id")

        if employee_id not in (sender, recipient):
            continue

        partner = recipient if sender == employee_id else sender
        timestamp = entity.attributes.get("timestamp", "")

        existing = latest_by_partner.get(partner)

        if not existing or timestamp > existing["timestamp"]:

            latest_by_partner[partner] = {
                "employee_id": partner,
                "timestamp": timestamp,
                "preview": entity.attributes.get("content", ""),
            }

    return sorted(
        latest_by_partner.values(),
        key=lambda item: item["timestamp"],
        reverse=True,
    )


def _display_name(employee_entity):

    if not employee_entity:
        return None

    attrs = employee_entity.attributes or {}

    if attrs.get("Name"):
        return attrs["Name"]

    if attrs.get("FirstName") and attrs.get("LastName"):
        return f"{attrs['FirstName']} {attrs['LastName']}"

    return None


def list_directory():
    """Every employee with a credential (employee_id + role + display name if the graph
    has an Employee entity for them) -- open to any authenticated employee (unlike
    core/auth_api.py's ADMIN-only roster, core/auth.py's CredentialStore.list_records())
    since picking a DM target isn't a privileged action. Deliberately strips everything
    CredentialStore.list_records() returns beyond employee_id/role -- no email,
    must_change_password, created_by/created_at -- since those are fine for an admin
    roster view but not for "who can I message" visible to every role."""

    # Imported here, not at module load time, purely to keep this module's import list
    # focused on what every other function actually needs -- core.auth has no
    # dependency on core.messaging, so there's no real circular-import risk either way.
    from core.auth import credential_store

    directory = []

    for record in credential_store.list_records():

        employee_id = record["employee_id"]
        employee_entity = ledger.get_entity(employee_id)

        directory.append(
            {
                "employee_id": employee_id,
                "role": record["role"],
                "name": _display_name(employee_entity),
            }
        )

    return directory
