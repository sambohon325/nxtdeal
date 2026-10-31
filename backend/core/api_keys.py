"""
core/api_keys.py -- Administration's "Identity & Access" item (Administration
Control Center rebuild, continued): real, per-employee API keys for
programmatic/integration access, distinct from core/auth.py's session tokens.

A session token (issue_token()) is short-lived (12h), issued at login, and
carries a role snapshot from that moment. An API key is meant for a script or
external integration to authenticate without a human logging in interactively
-- bound to the credential state at issuance. Password resets, role changes and
MFA revision changes invalidate the key. Legacy unbound keys require replacement;
there is no unsafe first-use migration. Keys expire after 90 days; route-specific
scopes remain separate work.

Only a SHA-256 hash of the key is ever stored (same "never store the
recoverable secret" discipline core/auth.py's password hashing already
established) -- the plaintext key is returned exactly once, at creation, and
is not recoverable afterward; only regenerating a new one is possible.

Real teeth, not just a management screen: api/app.py's `_authenticate()` (the
single choke point protecting every route in this backend) falls back to
verify_api_key() when a bearer token isn't a valid session token -- a real API
key genuinely authenticates a request, it isn't a hollow CRUD screen with
nothing behind it.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import API_KEY, EMPLOYEE

from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.auth import credential_store, _credential_binding

_KEY_PREFIX = "dos_"
KEY_LIFETIME = timedelta(days=90)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash_key(raw_key):
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key(employee_id, label, created_by):
    employee = ledger.get_entity(employee_id)
    if not employee or employee.entity_type != EMPLOYEE:
        return {"error": f"Employee '{employee_id}' not found"}

    record = credential_store.get_record(employee_id)
    if not record or record.get("must_change_password"):
        return {"error": "A current credential with a completed password change is required"}
    binding = _credential_binding(employee_id, record["role"])

    raw_secret = secrets.token_urlsafe(32)
    raw_key = f"{_KEY_PREFIX}{raw_secret}"
    key_hash = _hash_key(raw_key)

    key_id = id_generator.generate("APIK")
    issued_at = datetime.now(timezone.utc)
    entity = Entity(
        id=key_id,
        entity_type=API_KEY,
        attributes={
            "employee_id": employee_id,
            "label": label or "",
            "key_hash": key_hash,
            "credential_binding": binding,
            "last4": raw_key[-4:],
            "active": True,
            "created_by": created_by,
            "created_at": issued_at.isoformat(),
            "expires_at": (issued_at + KEY_LIFETIME).isoformat(),
            "last_used_at": None,
            "revoked_by": None,
            "revoked_at": None,
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    # The plaintext raw_key is only ever returned in THIS response.
    return {"id": entity.id, "raw_key": raw_key, **{k: v for k, v in entity.attributes.items() if k not in ("key_hash", "credential_binding")}}


def revoke_api_key(key_id, revoked_by):
    entity = ledger.get_entity(key_id)
    if not entity or entity.entity_type != API_KEY:
        return {"error": f"API key '{key_id}' not found"}

    if not entity.attributes.get("active"):
        return {"error": "This API key is already revoked"}

    entity.attributes["active"] = False
    entity.attributes["revoked_by"] = revoked_by
    entity.attributes["revoked_at"] = _now()
    save_graph(GRAPH_PATH)
    return _serialize(entity)


def _serialize(e):
    out = {k: v for k, v in e.attributes.items() if k not in ("key_hash", "credential_binding")}
    out["id"] = e.id
    return out


def list_api_keys_for_employee(employee_id):
    keys = [e for e in ledger.get_all().values() if e.entity_type == API_KEY and e.attributes.get("employee_id") == employee_id]
    keys.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [_serialize(e) for e in keys]


def list_all_api_keys():
    keys = [e for e in ledger.get_all().values() if e.entity_type == API_KEY]
    keys.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [_serialize(e) for e in keys]


def verify_api_key(raw_key):
    """Return the current principal only while its issuance binding still matches.

    Missing credentials, legacy keys and changed password/role/MFA state fail
    closed. Management serializers never return the internal binding.
    """

    if not isinstance(raw_key, str) or not raw_key.startswith(_KEY_PREFIX):
        return None

    key_hash = _hash_key(raw_key)

    for e in ledger.get_all().values():
        if e.entity_type == API_KEY and e.attributes.get("key_hash") == key_hash:
            if not e.attributes.get("active"):
                return None
            try:
                expiry = datetime.fromisoformat(e.attributes["expires_at"])
                if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                    return None
            except (KeyError, TypeError, ValueError, OverflowError):
                return None

            record = credential_store.get_record(e.attributes.get("employee_id"))
            if not record or record.get("must_change_password"):
                return None
            # Legacy unbound keys fail closed: silent first-use binding could
            # bless a stolen key after the owner has already reset credentials.
            binding = e.attributes.get("credential_binding")
            if not isinstance(binding, str) or not binding.isascii():
                return None
            try:
                current = _credential_binding(e.attributes["employee_id"], record["role"])
            except (ValueError, KeyError):
                return None
            if not hmac.compare_digest(binding, current):
                return None

            e.attributes["last_used_at"] = _now()
            # Deliberately not calling save_graph() here -- a last-used
            # timestamp update on every single authenticated request would
            # cost a real several-second save on this graph's size per call
            # (the same lesson this whole rebuild's sessions learned
            # repeatedly), so this field is best-effort/in-memory only until
            # the next unrelated save happens to persist it.
            return {"employee_id": e.attributes.get("employee_id"), "role": record["role"]}

    return None
