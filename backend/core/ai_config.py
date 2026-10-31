"""Generalized per-user, per-app AI model-selector config (2026-10-24).

This extends the MySales personal AI pattern (core/mysales_ai.py) to the entire
companion app suite. Any authenticated user can select how AI runs in their app:

  * off          -> the user (or admin) has turned AI off
  * byok         -> the user brings their own provider key (raw key never stored here)
  * on_device    -> prefer the native on-device model (routine tasks only)
  * dealer       -> fall back to the dealership's managed AI provider

Config is keyed by (app_slug, user_id) so each user can have different AI
preferences per app. MySales personal uses app_slug="mysales"; staff companion
apps (salesapp, reception, serviceops) use their slug with employee_id.
Customer-facing apps (showroom, mygarage, kiosk) use dealer-level config only --
no per-customer entity, since customers aren't authenticated.

resolve_model() returns the routing DECISION; the calling surface (currently
core/ai_assistant.py for the dashboard chat, or the Chrono Engine for
companion-app AI) executes it. This module never calls a model itself.

The raw BYOK key is masked to a last-4 hint and discarded -- never persisted.
The real secret belongs in a secret store on the surface that actually calls
the model.
"""

from datetime import datetime, timezone
from typing import Any

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import AI_CONFIG


# Providers a user can bring for BYOK (mirrors the dealer governor's, minus
# the managed/dealer-only ones). "local" covers on-device; "custom" points
# the user at their own endpoint.
BYOK_PROVIDERS = ("openai", "anthropic", "gemini", "azure_openai", "local", "custom", "other")

# Task kinds the router distinguishes. "routine" -> cheap tier, "premium" -> high-end tier.
TASK_KINDS = ("routine", "premium")

DEFAULT_ROUTINE_TIER = "gemini-flash-lite"
DEFAULT_PREMIUM_TIER = "gpt-4o"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _config_id(app_slug, user_id):
    return f"AIC-{app_slug}-{user_id}"


def _default_attributes(app_slug, user_id):
    return {
        "app_slug": app_slug,
        "user_id": user_id,
        "ai_enabled": True,
        # BYOK: provider + masked hint + configured flag. Raw key never stored here.
        "byok": {"provider": None, "key_masked": None, "configured": False},
        # Tiered routing preferences.
        "routing": {
            "on_device_when_available": True,
            "routine_tier": DEFAULT_ROUTINE_TIER,
            "premium_tier": DEFAULT_PREMIUM_TIER,
        },
        "updated_at": _now(),
    }


def _get_or_create(app_slug, user_id):
    cid = _config_id(app_slug, user_id)
    entity = ledger.get_entity(cid)
    if entity and entity.entity_type == AI_CONFIG:
        changed = False
        for key, value in _default_attributes(app_slug, user_id).items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True
        if changed:
            from core.storage import save_graph
            from core.storage_paths import GRAPH_PATH
            save_graph(GRAPH_PATH)
        return entity
    entity = Entity(id=cid, entity_type=AI_CONFIG, attributes=_default_attributes(app_slug, user_id))
    ledger.add_entity(entity)
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)
    return entity


def _save():
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)


def get_config(user_id, app_slug="mysales") -> dict[str, Any]:
    """Return the AI config for one user in one app. Creates defaults if absent.

    For MySales (app_slug="mysales") this delegates to core.mysales_ai.get_config
    so existing personal-account configs are preserved."""
    if not user_id:
        return {"error": "A user_id is required."}
    if app_slug == "mysales":
        from core import mysales_ai
        cfg = mysales_ai.get_config(user_id)
        return {
            "user_id": user_id,
            "app_slug": "mysales",
            "ai_enabled": cfg["ai_enabled"],
            "byok": cfg["byok"],
            "routing": cfg["routing"],
            "updated_at": cfg["updated_at"],
        }
    a = _get_or_create(app_slug, user_id).attributes
    routing: dict[str, Any] = dict(a.get("routing") or {})
    byok: dict[str, Any] = dict(a.get("byok") or {})
    return {
        "user_id": user_id,
        "app_slug": app_slug,
        "ai_enabled": bool(a.get("ai_enabled", True)),
        "byok": byok,
        "routing": routing,
        "updated_at": a.get("updated_at"),
    }


def set_ai_enabled(user_id, app_slug, enabled):
    """The user turns their AI on/off for this app.

    For MySales (app_slug="mysales") this delegates to core.mysales_ai.set_ai_enabled."""
    if not user_id:
        return {"error": "A user_id is required."}
    if app_slug == "mysales":
        from core import mysales_ai
        return mysales_ai.set_ai_enabled(user_id, enabled)
    e = _get_or_create(app_slug, user_id)
    e.attributes["ai_enabled"] = bool(enabled)
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(user_id, app_slug)


def _mask(key):
    key = (key or "").strip()
    if len(key) < 4:
        return "••••"
    return "••••" + key[-4:]


def set_byok(user_id, app_slug, provider, api_key):
    """Store the user's BYOK setup. The raw key is masked to a last-4 hint and discarded -- never
    persisted. Pass api_key='' to keep the provider but mark not-configured.

    For MySales (app_slug="mysales") this delegates to core.mysales_ai.set_byok."""
    if not user_id:
        return {"error": "A user_id is required."}
    if app_slug == "mysales":
        from core import mysales_ai
        return mysales_ai.set_byok(user_id, provider, api_key)
    if provider not in BYOK_PROVIDERS:
        return {"error": f"Unknown provider '{provider}'. Valid: {list(BYOK_PROVIDERS)}"}
    e = _get_or_create(app_slug, user_id)
    key = (api_key or "").strip()
    e.attributes["byok"] = {
        "provider": provider,
        "key_masked": _mask(key) if key else None,
        "configured": bool(key),
    }
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(user_id, app_slug)


def clear_byok(user_id, app_slug):
    if not user_id:
        return {"error": "A user_id is required."}
    if app_slug == "mysales":
        from core import mysales_ai
        return mysales_ai.clear_byok(user_id)
    e = _get_or_create(app_slug, user_id)
    e.attributes["byok"] = {"provider": None, "key_masked": None, "configured": False}
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(user_id, app_slug)


def set_routing(user_id, app_slug, on_device_when_available=None, routine_tier=None, premium_tier=None):
    if not user_id:
        return {"error": "A user_id is required."}
    if app_slug == "mysales":
        from core import mysales_ai
        return mysales_ai.set_routing(user_id, on_device_when_available, routine_tier, premium_tier)
    e = _get_or_create(app_slug, user_id)
    routing = e.attributes.setdefault("routing", {
        "on_device_when_available": True,
        "routine_tier": DEFAULT_ROUTINE_TIER,
        "premium_tier": DEFAULT_PREMIUM_TIER,
    })
    if on_device_when_available is not None:
        routing["on_device_when_available"] = bool(on_device_when_available)
    if routine_tier is not None:
        routing["routine_tier"] = str(routine_tier).strip() or DEFAULT_ROUTINE_TIER
    if premium_tier is not None:
        routing["premium_tier"] = str(premium_tier).strip() or DEFAULT_PREMIUM_TIER
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(user_id, app_slug)


def resolve_model(user_id, app_slug="mysales", task_kind="routine"):
    """The routing DECISION for one AI task in one app, in priority order:
      1. AI off (user or admin disabled)  -> source 'off'
      2. BYOK configured                   -> the user's own provider + the tier's model
      3. On-device preferred + routine task -> source 'on_device' (native app runs it; zero cloud cost)
      4. Otherwise                        -> the dealer/managed provider + the tier's model

    The caller executes the decision; this module never calls a model itself.

    For MySales (app_slug="mysales") this delegates to core.mysales_ai's
    resolve_model for backward compatibility with existing personal-account configs."""
    if task_kind not in TASK_KINDS:
        task_kind = "routine"

    # Delegate to mysales_ai for the personal app to preserve existing configs.
    if app_slug == "mysales":
        from core import mysales_ai
        return mysales_ai.resolve_model(user_id, task_kind)

    cfg = get_config(user_id, app_slug)
    if "error" in cfg:
        return {"source": "off", "reason": cfg["error"]}
    if not cfg["ai_enabled"]:
        return {"source": "off", "reason": "AI is turned off for this app."}

    routing = cfg["routing"]
    model = routing["routine_tier"] if task_kind == "routine" else routing["premium_tier"]
    byok = cfg["byok"]

    if byok.get("configured"):
        return {
            "source": "byok",
            "provider": byok.get("provider"),
            "model": model,
            "task_kind": task_kind,
            "app_slug": app_slug,
            "reason": "Using the user's own key.",
        }

    if routing.get("on_device_when_available") and task_kind == "routine":
        return {
            "source": "on_device",
            "model": "on-device",
            "task_kind": task_kind,
            "app_slug": app_slug,
            "reason": "Routine task -> native on-device model when the app supports it (no cloud cost).",
        }

    # Fall back to the dealer's provider (managed 'dealeros' if the dealer holds the add-on,
    # else whatever the dealer governor is set to). Cost/entitlement is the dealer's.
    dealer_provider = "dealeros"
    try:
        from core import ai_spend
        dealer_provider = ai_spend.get_policy().get("provider", "openai")
    except Exception:
        pass
    return {
        "source": "dealer",
        "provider": dealer_provider,
        "model": model,
        "task_kind": task_kind,
        "app_slug": app_slug,
        "reason": "No personal key; routed to the dealership's AI provider.",
    }
