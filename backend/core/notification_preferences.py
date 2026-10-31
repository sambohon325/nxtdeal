"""
core/notification_preferences.py -- per-employee notification toggles (session 74).
Sam: "when clicked, it should show user profile settings / password administration,
notification settings." Mirrors core/dashboard_layouts.py's pattern almost exactly:
one NotificationPreference entity per employee_id, real save/load, no separate store.

Honest scope note (matches this codebase's established convention of never faking a
capability): nothing downstream currently reads these preferences to actually gate
delivery -- compliance-alert DMs (core/compliance.py), workflow-instance updates, and
channel/DM messages (core/messaging.py) all still fire unconditionally today. This
module is real, persisted preference *storage*; wiring it into the actual delivery
paths is a separate, larger change flagged for later rather than silently assumed here.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import NOTIFICATION_PREFERENCE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 74) --
# every real saved notification preference had been silently discarded on server
# restart. Fixed below.

# The real, named categories this pass covers -- deliberately tied to features that
# actually exist in this codebase (compliance alerts, workflow instances, direct
# messages, channel messages, the agentic bot's task suggestions) rather than invented
# generic categories with nothing behind them.
PREFERENCE_KEYS = (
    "compliance_alerts",
    "workflow_updates",
    "direct_messages",
    "channel_messages",
    "bot_suggestions",
)

DEFAULTS = {key: True for key in PREFERENCE_KEYS}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find(employee_id):
    for entity in ledger.get_all().values():
        if (
            entity.entity_type == NOTIFICATION_PREFERENCE
            and entity.attributes.get("employee_id") == employee_id
        ):
            return entity
    return None


def _serialize(entity):
    attrs = entity.attributes
    prefs = {key: attrs.get(key, DEFAULTS[key]) for key in PREFERENCE_KEYS}
    return {"preferences": prefs, "updated_at": attrs.get("updated_at")}


def get_preferences(employee_id):
    """Real defaults (all on) for an employee who's never saved a preference yet --
    not an error state, same "empty board is valid" convention as
    core/dashboard_layouts.py's get_layout()."""

    entity = _find(employee_id)

    if not entity:
        return {"preferences": dict(DEFAULTS), "updated_at": None}

    return _serialize(entity)


def save_preferences(employee_id, preferences):
    """Full replace of the known keys -- unknown keys in the incoming dict are
    silently dropped (never persisted), matching core/dashboard_layouts.py's
    _clean_module()'s whitelist-only approach rather than trusting arbitrary client
    input onto the graph."""

    clean = {}
    for key in PREFERENCE_KEYS:
        value = preferences.get(key) if isinstance(preferences, dict) else None
        clean[key] = bool(value) if value is not None else DEFAULTS[key]

    entity = _find(employee_id)

    if entity:
        entity.attributes.update(clean)
        entity.attributes["updated_at"] = _now()
    else:
        entity = Entity(
            id=id_generator.generate("NOTIF"),
            entity_type=NOTIFICATION_PREFERENCE,
            attributes={
                "employee_id": employee_id,
                "updated_at": _now(),
                **clean,
            },
        )
        ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return _serialize(entity)
