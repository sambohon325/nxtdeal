"""
Per-tenant provider credentials + adapter factory (Track B, 2026-07-25).

integrations_registry.py has the seam (register_adapter / is_live) but no way to STORE the
credentials a real adapter needs, and no way for an admin to flip a capability live without
a code change. This module is that missing half:

  * a ProviderCredential store (ADMIN-only, secrets masked on read) holding, per capability,
    the chosen provider + a non-secret config dict + a secrets dict;
  * an adapter FACTORY -- ADAPTER_BUILDERS maps a provider name to a builder that turns
    (config, secrets) into the callable the seam expects -- so configuring a credential for a
    provider we have a builder for REGISTERS a live adapter and the capability goes live;
  * one genuinely functional, network-real builder: `http_webhook` for notifications, which
    POSTs the message payload to a configured URL (usable today with any endpoint the dealer
    controls -- their own webhook, a Zapier/Make hook, etc. -- with NO paid provider account).

Named-provider builders (Twilio, SendGrid, Meta, Google) are intentionally left as clearly
marked slots: constructing and verifying their real API calls needs live accounts, so rather
than ship an unverified integration we register the slot and document exactly what a builder
must return. Until a builder is filled in and credentials configured, the capability stays
honestly simulated.

Note: register_adapter writes a process-global slot in integrations_registry, matching this
codebase's single-tenant-per-process model.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import PROVIDER_CREDENTIAL
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import integrations_registry


def _now():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------
# Adapter builders: provider_name -> builder(config, secrets) -> callable seam adapter.
# --------------------------------------------------------------------------------------

def _http_post(url, payload, headers, timeout=10):
    """Real HTTP POST (stdlib, no dependency). Isolated so tests can monkeypatch it
    without touching the network. Returns (status_code, body_text)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _build_http_webhook_notifications(config, secrets):
    """A real notifications adapter that POSTs each message to a configured webhook URL.
    Works today with any endpoint the dealer controls -- no paid provider account needed.
    config: {"url": "..."}; secrets: {"auth_header": "Bearer ..."} (optional)."""
    url = (config or {}).get("url")
    if not url:
        raise ValueError("http_webhook notifications requires config.url")
    auth = (secrets or {}).get("auth_header")

    def adapter(to, event, channels):
        headers = {"Authorization": auth} if auth else {}
        payload = {"to": to, "event": event, "channels": list(channels)}
        try:
            code, body = _http_post(url, payload, headers)
            ok = 200 <= code < 300
            return {
                "capability": "notifications", "provider": "http_webhook",
                "simulated": False, "delivered": ok, "status_code": code,
                "to": to, "channels": list(channels), "at": _now(),
            }
        except Exception as exc:
            return {
                "capability": "notifications", "provider": "http_webhook",
                "simulated": False, "delivered": False, "error": str(exc),
                "to": to, "channels": list(channels), "at": _now(),
            }

    return adapter


# Builders we can honestly ship. Keyed (capability, provider_name).
ADAPTER_BUILDERS = {
    ("notifications", "http_webhook"): _build_http_webhook_notifications,
}

# Named providers we recommend but can't verify without live accounts. Listed so the UI can
# offer them and explain they need a builder + credentials before they go live.
PROVIDER_SLOTS = {
    "notifications": ["http_webhook", "twilio", "sendgrid"],
    "payments": ["stripe"],
    "identity": ["stripe_identity", "persona"],
    "insurance": ["insurance_api"],
    "credit_bureau": ["experian", "equifax", "transunion"],
    "banking": ["plaid"],
    "enrichment": ["http_webhook", "experian", "acxiom"],
    "ads": ["meta", "google"],
    "telephony": ["twilio", "ringcentral"],
    "esignature": ["docusign", "dropbox_sign", "adobe_sign"],
}

_SECRET_KEYS_HINT = ("auth_header", "api_key", "api_secret", "token", "account_sid", "auth_token", "password")


def _mask(value):
    if not value:
        return value
    s = str(value)
    if len(s) <= 4:
        return "****"
    return "****" + s[-4:]


def _mask_secrets(secrets):
    return {k: _mask(v) for k, v in (secrets or {}).items()}


# --------------------------------------------------------------------------------------
# Credential store
# --------------------------------------------------------------------------------------

def _find_credential(capability):
    for e in ledger.get_all().values():
        if e.entity_type == PROVIDER_CREDENTIAL and e.attributes.get("capability") == capability and not e.attributes.get("deleted"):
            return e
    return None


def _has_builder(capability, provider):
    return (capability, provider) in ADAPTER_BUILDERS


def _try_register(capability, provider, config, secrets):
    """If we have a builder for this (capability, provider), build + register the adapter so
    the capability goes live. Returns (live: bool, error: str|None)."""
    builder = ADAPTER_BUILDERS.get((capability, provider))
    if not builder:
        return False, None
    try:
        adapter = builder(config or {}, secrets or {})
        integrations_registry.register_adapter(capability, adapter)
        return True, None
    except Exception as exc:
        return False, str(exc)


def configure_credential(capability, provider, config, secrets, admin_id):
    """Store (or replace) the credential for a capability and, if a builder exists for the
    provider, register a live adapter. Secrets are stored but never returned unmasked."""
    if capability not in integrations_registry.CAPABILITIES:
        return {"error": f"Unknown capability '{capability}'"}

    existing = _find_credential(capability)
    if existing:
        entity = existing
    else:
        entity = Entity(
            id=id_generator.generate("PCRED"),
            entity_type=PROVIDER_CREDENTIAL,
            attributes={"capability": capability, "created_at": _now()},
        )
        ledger.add_entity(entity)

    entity.attributes.update({
        "provider": provider,
        "config": dict(config or {}),
        "secrets": dict(secrets or {}),
        "configured_by": admin_id,
        "updated_at": _now(),
        "deleted": False,
    })

    live, err = _try_register(capability, provider, config, secrets)
    entity.attributes["has_builder"] = _has_builder(capability, provider)
    entity.attributes["registration_error"] = err
    save_graph(GRAPH_PATH)

    return {
        "capability": capability,
        "provider": provider,
        "live": integrations_registry.is_live(capability),
        "has_builder": _has_builder(capability, provider),
        "registration_error": err,
        "note": (
            "Live -- an adapter is registered and this capability now sends for real."
            if live else
            "Stored. No shippable adapter builder exists for this provider yet, so the "
            "capability stays simulated until one is added (or use provider 'http_webhook' "
            "for notifications, which works today with any endpoint you control)."
        ),
    }


def _serialize(entity):
    a = entity.attributes
    return {
        "id": entity.id,
        "capability": a.get("capability"),
        "provider": a.get("provider"),
        "config": a.get("config", {}),
        "secrets": _mask_secrets(a.get("secrets", {})),
        "has_builder": a.get("has_builder", False),
        "live": integrations_registry.is_live(a.get("capability")),
        "configured_by": a.get("configured_by"),
        "updated_at": a.get("updated_at"),
    }


def list_credentials():
    creds = [
        e for e in ledger.get_all().values()
        if e.entity_type == PROVIDER_CREDENTIAL and not e.attributes.get("deleted")
    ]
    return [_serialize(c) for c in sorted(creds, key=lambda e: e.attributes.get("capability", ""))]


def get_credential(capability):
    c = _find_credential(capability)
    return _serialize(c) if c else None


def remove_credential(capability):
    """Delete the stored credential and take the capability back to simulated."""
    c = _find_credential(capability)
    if not c:
        return {"error": "No credential for that capability"}
    c.attributes["deleted"] = True
    c.attributes["updated_at"] = _now()
    # Take the capability offline (back to simulated).
    integrations_registry._ADAPTERS.pop(capability, None)
    save_graph(GRAPH_PATH)
    return {"ok": True, "capability": capability, "live": integrations_registry.is_live(capability)}


def provider_slots():
    """The providers offered per capability, flagging which have a shippable builder."""
    return {
        cap: [{"provider": p, "has_builder": _has_builder(cap, p)} for p in providers]
        for cap, providers in PROVIDER_SLOTS.items()
    }


def activate_from_store():
    """Register adapters for every stored credential (e.g. on process start). Returns the
    number of capabilities taken live. Safe to call repeatedly."""
    live = 0
    for e in ledger.get_all().values():
        if e.entity_type != PROVIDER_CREDENTIAL or e.attributes.get("deleted"):
            continue
        cap = e.attributes.get("capability")
        ok, _ = _try_register(cap, e.attributes.get("provider"), e.attributes.get("config"), e.attributes.get("secrets"))
        if ok:
            live += 1
    return live
