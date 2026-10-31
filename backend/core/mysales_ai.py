"""
core/mysales_ai.py -- MySales personal AI config + tiered routing (Freemium Platform roadmap,
Phase 5+, 2026-08-03).

MySales is the rep's personal cockpit and is personal-account-scoped (the personal-tools layer,
alongside their own Plaid bank link) -- independent of whether their dealership has adopted NXTDeal.
So a rep's AI setup is PER-REP, not per-dealer, and lives here rather than in the dealer's spend
governor (core/ai_spend.py).

This implements the low-cost / flexible architecture Sam sketched for the MySales AI coach/assistant:

  * On-device when available -- the rep can prefer the phone's native on-device model for simple
    tasks (summaries, intent) at zero cloud cost. (The native iOS/Android app honors this; this web
    backend records the preference and routes around it -- it can't run an on-device model itself.)
  * Bring-your-own-key (BYOK) -- an advanced rep can drop in their own OpenAI / Anthropic / Gemini
    key to power high-end models on their own dime. The raw key is NEVER stored here (only the
    provider + a masked last-4 hint + a "configured" flag); the real secret belongs in a secret
    store on the surface that actually calls the model.
  * Tiered routing -- routine tasks route to a cheap tier (e.g. Gemini Flash-Lite), premium tasks to
    a high-end tier (e.g. GPT-4o). resolve_model() returns the routing DECISION; the calling surface
    executes it.

A rep can also just turn their AI off entirely (some people don't want it) -- resolve_model then
returns an 'off' decision and the MySales AI surfaces hide.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import MYSALES_AI_CONFIG


# BYOK providers a rep can bring (mirrors the dealer governor's, minus the managed/dealer-only ones).
BYOK_PROVIDERS = ("openai", "anthropic", "gemini", "azure_openai", "other")

# Task kinds the router distinguishes. "routine" -> cheap tier, "premium" -> high-end tier.
TASK_KINDS = ("routine", "premium")

DEFAULT_ROUTINE_TIER = "gemini-flash-lite"
DEFAULT_PREMIUM_TIER = "gpt-4o"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _config_id(rep_id):
    return f"MSAI-{rep_id}"


def _default_attributes(rep_id):
    return {
        "rep_id": rep_id,
        "ai_enabled": True,  # the rep's own AI on/off for MySales
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


def _get_or_create(rep_id):
    cid = _config_id(rep_id)
    entity = ledger.get_entity(cid)
    if entity and entity.entity_type == MYSALES_AI_CONFIG:
        changed = False
        for key, value in _default_attributes(rep_id).items():
            if key not in entity.attributes:
                entity.attributes[key] = value
                changed = True
        if changed:
            from core.storage import save_graph
            from core.storage_paths import GRAPH_PATH
            save_graph(GRAPH_PATH)
        return entity
    entity = Entity(id=cid, entity_type=MYSALES_AI_CONFIG, attributes=_default_attributes(rep_id))
    ledger.add_entity(entity)
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)
    return entity


def _save():
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)


def get_config(rep_id):
    if not rep_id:
        return {"error": "A rep_id is required."}
    a = _get_or_create(rep_id).attributes
    return {
        "rep_id": rep_id,
        "ai_enabled": bool(a.get("ai_enabled", True)),
        "byok": dict(a.get("byok", {})),
        "routing": dict(a.get("routing", {})),
        "updated_at": a.get("updated_at"),
    }


def set_ai_enabled(rep_id, enabled):
    """The rep turns their MySales AI on/off."""
    e = _get_or_create(rep_id)
    e.attributes["ai_enabled"] = bool(enabled)
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(rep_id)


def _mask(key):
    key = (key or "").strip()
    if len(key) < 4:
        return "••••"
    return "••••" + key[-4:]


def set_byok(rep_id, provider, api_key):
    """Store the rep's BYOK setup. The raw key is masked to a last-4 hint and discarded -- never
    persisted. Pass api_key='' to keep the provider but mark not-configured."""
    if provider not in BYOK_PROVIDERS:
        return {"error": f"Unknown provider '{provider}'. Valid: {list(BYOK_PROVIDERS)}"}
    e = _get_or_create(rep_id)
    key = (api_key or "").strip()
    e.attributes["byok"] = {
        "provider": provider,
        "key_masked": _mask(key) if key else None,
        "configured": bool(key),
    }
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(rep_id)


def clear_byok(rep_id):
    e = _get_or_create(rep_id)
    e.attributes["byok"] = {"provider": None, "key_masked": None, "configured": False}
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(rep_id)


def set_routing(rep_id, on_device_when_available=None, routine_tier=None, premium_tier=None):
    e = _get_or_create(rep_id)
    routing = e.attributes.setdefault("routing", {})
    if on_device_when_available is not None:
        routing["on_device_when_available"] = bool(on_device_when_available)
    if routine_tier is not None:
        routing["routine_tier"] = str(routine_tier).strip() or DEFAULT_ROUTINE_TIER
    if premium_tier is not None:
        routing["premium_tier"] = str(premium_tier).strip() or DEFAULT_PREMIUM_TIER
    e.attributes["updated_at"] = _now()
    _save()
    return get_config(rep_id)


def resolve_model(rep_id, task_kind="routine"):
    """The routing DECISION for one AI task, in priority order:
      1. AI off (rep opted out)      -> source 'off'
      2. BYOK configured             -> the rep's own provider + the tier's model
      3. On-device preferred + routine task -> source 'on_device' (native app runs it; zero cloud cost)
      4. Otherwise                   -> the dealer/managed provider + the tier's model
    The caller executes the decision; this module never calls a model itself."""
    if task_kind not in TASK_KINDS:
        task_kind = "routine"
    cfg = get_config(rep_id)
    if not cfg["ai_enabled"]:
        return {"source": "off", "reason": "The rep has AI turned off in MySales."}

    routing = cfg["routing"]
    model = routing["routine_tier"] if task_kind == "routine" else routing["premium_tier"]
    byok = cfg["byok"]

    if byok.get("configured"):
        return {
            "source": "byok",
            "provider": byok.get("provider"),
            "model": model,
            "task_kind": task_kind,
            "reason": "Using the rep's own key.",
        }

    if routing.get("on_device_when_available") and task_kind == "routine":
        return {
            "source": "on_device",
            "model": "on-device",
            "task_kind": task_kind,
            "reason": "Routine task -> native on-device model when the app supports it (no cloud cost).",
        }

    # Fall back to the dealer's provider (managed 'dealeros' if the dealership holds the add-on, else
    # whatever the dealer governor is set to). Cost/entitlement is the dealer's, not the rep's.
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
        "reason": "No personal key; routed to the dealership's AI provider.",
    }
