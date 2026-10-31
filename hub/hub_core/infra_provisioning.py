"""
Dealer infrastructure auto-provisioning (2026-07-24, Sam: "spin dealerships up automatically ...
auto created in coolify ... the less I have to deal with coolify the better").

`create_dealer` already does the LOGICAL provisioning (registry record, tenant storage dir, admin
login). This module does the INFRASTRUCTURE half: it calls the Coolify API (hub_core/coolify.py)
to create + deploy a dealer's two apps, then records the resulting api_base_url back on the dealer
so apps.nxtdeal.app can route to it. One Hub action, no Coolify clicking.

For a dealer with slug `dealerN` it creates:
  • dealerN-api      — base `/backend`, port 8000, uvicorn start, per-tenant env + a persistent
                       volume for its storage, domain dealerN-api.<base>
  • dealerN-frontend — base `/frontend`, build-time NEXT_PUBLIC_API_URL → the api, domain dealerN.<base>

Then it deploys both and writes api_base_url onto the dealer. Progress + failures are tracked per
dealer in infra_provisioning_storage so the Hub console can show status and offer a retry. Safe by
default: if Coolify isn't configured (no COOLIFY_* env on hub-api) it returns a clear error and
changes nothing, so the manual flow still works.
"""

import os
import secrets as pysecrets
from datetime import datetime, timezone

from hub_core.dealer_registry import registry
from hub_core.dealer_storage import save_dealers
from hub_core.provisioning import set_dealer_api_base_url
from hub_core import coolify
from hub_core import infra_provisioning_storage as store

DEALERS_PATH = "storage/dealers.json"
PROVISIONING_PATH = store.PROVISIONING_PATH


def _now():
    return datetime.now(timezone.utc).isoformat()


def _network_key():
    return os.environ.get("DEALEROS_NETWORK_KEY", "")


def _openai_key():
    # A key to hand each dealer-api for its AI features (optional). A dealer-specific var wins.
    return os.environ.get("COOLIFY_DEALER_OPENAI_KEY") or os.environ.get("OPENAI_API_KEY", "")


def _storage_mount(storage_dir):
    # Where the dealer-api container should mount its persistent volume. The exact container path
    # depends on the Nixpacks working dir, so it's overridable; default assumes /app + the tenant's
    # relative storage dir. Verify against your Coolify/Nixpacks build once (see the warning we
    # attach to the provisioning record).
    base = os.environ.get("COOLIFY_DEALER_STORAGE_MOUNT_BASE", "/app")
    return f"{base.rstrip('/')}/{storage_dir}"


def _persist(dealer_id, record):
    store.put(dealer_id, record)
    store.save_provisioning(PROVISIONING_PATH)


def _fail(dealer_id, record, msg):
    record.update({"status": "failed", "error": msg, "updated_at": _now()})
    _persist(dealer_id, record)
    return {"error": msg, "status": "failed", "dealer_id": dealer_id}


def provision_dealer(dealer_id, force=False):
    """Create + deploy a dealer's frontend + API in Coolify and record its api_base_url.

    Idempotent: if this dealer already has both apps (or a provisioning run is in flight), it
    returns the existing record instead of creating a SECOND pair of Coolify apps (which would
    orphan the first and mint a divergent auth secret). A retry after a PARTIAL success reuses the
    app uuids already recorded rather than re-creating. Pass force=True to bypass and re-create."""
    if not coolify.is_configured():
        return {"error": "Coolify auto-provisioning isn't configured on hub-api. Missing env: "
                         + ", ".join(coolify.missing_config())}

    dealer = registry.get(dealer_id)
    if dealer is None:
        return {"error": f"Dealer '{dealer_id}' not found."}

    slug = dealer.slug
    record = store.get(dealer_id) or {"dealer_id": dealer_id, "slug": slug, "warnings": []}
    record.setdefault("warnings", [])

    # Idempotency guards — don't spin up duplicate apps for a dealer that's already provisioned or
    # has a run in progress (the auto-provision-on-create hook and a manual "Provision" click can
    # otherwise both fire).
    if not force:
        if record.get("api_app_uuid") and record.get("fe_app_uuid") and record.get("status") in ("deploying", "provisioned", "ready"):
            return {"dealer_id": dealer_id, "slug": slug, "status": record.get("status"),
                    "api_app_uuid": record.get("api_app_uuid"), "fe_app_uuid": record.get("fe_app_uuid"),
                    "api_url": record.get("api_url"), "frontend_url": record.get("frontend_url"),
                    "warnings": record.get("warnings", []), "already_provisioned": True}
        if record.get("status") == "provisioning":
            return {"dealer_id": dealer_id, "slug": slug, "status": "provisioning", "already_in_progress": True}

    record.update({"status": "provisioning", "error": None, "updated_at": _now()})
    _persist(dealer_id, record)

    api_dom = coolify.api_domain(slug)
    fe_dom = coolify.frontend_domain(slug)

    # 1) dealer-api — reuse an app already created by a prior partial run rather than duplicating it.
    api_uuid = record.get("api_app_uuid")
    if not api_uuid:
        api_uuid, err = coolify.create_application(
            name=f"{slug}-api",
            base_directory="/backend",
            ports_exposes=8000,
            domain=api_dom,
            start_command="uvicorn api.app:app --host 0.0.0.0 --port 8000",
        )
        if err:
            return _fail(dealer_id, record, f"create {slug}-api: {err}")
        record.update({"api_app_uuid": api_uuid, "api_url": api_dom})
        _persist(dealer_id, record)

    auth_secret = pysecrets.token_urlsafe(32)
    _, err = coolify.set_envs(api_uuid, [
        ("DEALEROS_STORAGE_DIR", dealer.storage_dir, False),
        ("DEALEROS_AUTH_SECRET", auth_secret, False),
        ("DEALEROS_NETWORK_KEY", _network_key(), False),
        ("OPENAI_API_KEY", _openai_key(), False),
    ])
    if err:
        return _fail(dealer_id, record, f"{slug}-api env: {err}")

    # Persistent volume so the dealer's data survives redeploys — best-effort (endpoint/path are
    # the most Coolify-version-sensitive bits), recorded as a warning rather than a hard failure.
    _, verr = coolify.add_persistent_storage(api_uuid, _storage_mount(dealer.storage_dir), f"{slug}-storage")
    if verr:
        record["warnings"].append(
            f"persistent storage not auto-added ({verr}). Add a volume for the storage dir in Coolify "
            f"so this dealer's data survives redeploys, and confirm the mount path."
        )
        _persist(dealer_id, record)

    _, err = coolify.deploy(api_uuid)
    if err:
        return _fail(dealer_id, record, f"deploy {slug}-api: {err}")

    # 2) dealer-frontend — likewise reuse an already-created app on retry.
    fe_uuid = record.get("fe_app_uuid")
    if not fe_uuid:
        fe_uuid, err = coolify.create_application(
            name=f"{slug}-frontend",
            base_directory="/frontend",
            ports_exposes=3000,
            domain=fe_dom,
        )
        if err:
            return _fail(dealer_id, record, f"create {slug}-frontend: {err}")
        record.update({"fe_app_uuid": fe_uuid, "frontend_url": fe_dom})
        _persist(dealer_id, record)

    # NEXT_PUBLIC_API_URL MUST be build-time (baked into the Next bundle).
    _, err = coolify.set_envs(fe_uuid, [("NEXT_PUBLIC_API_URL", api_dom, True)])
    if err:
        return _fail(dealer_id, record, f"{slug}-frontend env: {err}")
    _, err = coolify.deploy(fe_uuid)
    if err:
        return _fail(dealer_id, record, f"deploy {slug}-frontend: {err}")

    # 3) Record api_base_url on the dealer — this is what apps.nxtdeal.app's resolver reads.
    set_dealer_api_base_url(dealer_id, api_dom)
    save_dealers(DEALERS_PATH)

    record.update({"status": "deploying", "error": None, "updated_at": _now()})
    _persist(dealer_id, record)

    return {
        "dealer_id": dealer_id,
        "slug": slug,
        "status": "deploying",
        "api": {"uuid": api_uuid, "url": api_dom},
        "frontend": {"uuid": fe_uuid, "url": fe_dom},
        "warnings": record.get("warnings", []),
        "note": ("Both apps created and deploying in Coolify; api_base_url recorded so "
                 "apps.nxtdeal.app routes to this dealer once the build goes live. "
                 "Deploys take a few minutes — poll provision-status."),
    }


def get_status(dealer_id, live=False):
    record = store.get(dealer_id)
    if record is None:
        return {"error": "No provisioning on file for this dealer yet.", "status": "none"}
    out = dict(record)
    if live and coolify.is_configured():
        out["live"] = {}
        for key, uuid_key in (("api", "api_app_uuid"), ("frontend", "fe_app_uuid")):
            uuid = record.get(uuid_key)
            if uuid:
                data, err = coolify.get_application(uuid)
                out["live"][key] = (data or {}).get("status") if not err else f"unknown ({err})"
    return out


def provisioning_config():
    return {"configured": coolify.is_configured(), "missing": coolify.missing_config()}
