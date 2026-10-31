"""
Coolify REST API client (2026-07-24, Sam: "spin dealerships up automatically ... auto created
in coolify ... the less I have to deal with coolify the better"). A thin, config-driven client
the Hub uses to CREATE and DEPLOY a new dealer's frontend + API as Coolify applications, so
provisioning a dealer goes from a manual Coolify checklist to one Hub action.

Everything is read live from env (never cached at import) so hub-api can be reconfigured without
a rebuild, and so it's monkeypatchable in tests. Nothing here is dealer-specific — the
orchestration (hub_core/infra_provisioning.py) composes these calls per dealer.

Targets the Coolify v4 REST API (`/api/v1`). Endpoint paths + payload field names are centralized
in the methods below and commented, so if a Coolify release renames a field it's a one-line fix.
Uses stdlib urllib (same as hub_core/dealer_ai_kill_switch.py) — no new dependency.

Required env on hub-api to enable auto-provisioning:
  COOLIFY_API_URL           e.g. https://coolify.yourhost.com   (the Coolify instance; API at /api/v1)
  COOLIFY_API_TOKEN         a Coolify API token (Bearer)
  COOLIFY_PROJECT_UUID      the project new dealer apps live in
  COOLIFY_SERVER_UUID       the server to deploy on
  COOLIFY_GITHUB_APP_UUID   the connected private GitHub App source for this repo
Optional:
  COOLIFY_ENVIRONMENT_NAME  default "production"
  COOLIFY_GIT_REPOSITORY    default "sambohon325/dealerOS"
  COOLIFY_GIT_BRANCH        default "main"
  COOLIFY_DOMAIN_BASE       default "nxtdeal.app"   (used to build dealer{N}.<base> / dealer{N}-api.<base>)
"""

import json
import os
import urllib.error
import urllib.request

_TIMEOUT = 30


def _env(name, default=None):
    return os.environ.get(name, default)


def config():
    return {
        "api_url": (_env("COOLIFY_API_URL", "") or "").rstrip("/"),
        "token": _env("COOLIFY_API_TOKEN", ""),
        "project_uuid": _env("COOLIFY_PROJECT_UUID", ""),
        "server_uuid": _env("COOLIFY_SERVER_UUID", ""),
        "github_app_uuid": _env("COOLIFY_GITHUB_APP_UUID", ""),
        "environment_name": _env("COOLIFY_ENVIRONMENT_NAME", "production"),
        "git_repository": _env("COOLIFY_GIT_REPOSITORY", "sambohon325/dealerOS"),
        "git_branch": _env("COOLIFY_GIT_BRANCH", "main"),
        "domain_base": _env("COOLIFY_DOMAIN_BASE", "nxtdeal.app"),
    }


def is_configured():
    c = config()
    return all(c[k] for k in ("api_url", "token", "project_uuid", "server_uuid", "github_app_uuid"))


def missing_config():
    c = config()
    return [k for k in ("api_url", "token", "project_uuid", "server_uuid", "github_app_uuid") if not c[k]]


def _request(method, path, body=None):
    """Call the Coolify API. Returns (data, error). `path` is relative to /api/v1."""
    c = config()
    if not c["api_url"] or not c["token"]:
        return None, "Coolify isn't configured (COOLIFY_API_URL / COOLIFY_API_TOKEN)."
    url = f"{c['api_url']}/api/v1{path}"
    data_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data_bytes,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {c['token']}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        # Coolify returns a JSON error body on 4xx/5xx — surface it.
        try:
            detail = json.loads(error.read().decode("utf-8"))
            detail = detail.get("message") or detail.get("error") or detail
        except Exception:
            detail = str(error)
        return None, f"Coolify {error.code}: {detail}"
    except urllib.error.URLError as error:
        return None, f"Coolify unreachable: {error}"

    if not raw:
        return {}, None
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, ValueError) as error:
        return None, f"bad Coolify response: {error}"


# ---------------------------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------------------------

def create_application(name, base_directory, ports_exposes, domain,
                       build_pack="nixpacks", start_command=None):
    """Create an app from the connected private GitHub App repo. Returns (uuid, error).
    POST /applications/private-github-app (Coolify v4)."""
    c = config()
    payload = {
        "project_uuid": c["project_uuid"],
        "server_uuid": c["server_uuid"],
        "environment_name": c["environment_name"],
        "github_app_uuid": c["github_app_uuid"],
        "git_repository": c["git_repository"],
        "git_branch": c["git_branch"],
        "build_pack": build_pack,
        "ports_exposes": str(ports_exposes),
        "base_directory": base_directory,
        "domains": domain,
        "name": name,
        "instant_deploy": False,
    }
    if start_command:
        # Coolify field for a custom Nixpacks start command.
        payload["custom_start_command"] = start_command
    data, error = _request("POST", "/applications/private-github-app", payload)
    if error:
        return None, error
    uuid = (data or {}).get("uuid") or (data or {}).get("application_uuid")
    if not uuid:
        return None, f"Coolify created no application uuid (response: {data})."
    return uuid, None


def set_env(app_uuid, key, value, is_build_time=False):
    """Set one env var. POST /applications/{uuid}/envs. is_build_time matters for NEXT_PUBLIC_*."""
    return _request("POST", f"/applications/{app_uuid}/envs", {
        "key": key,
        "value": "" if value is None else str(value),
        "is_build_time": bool(is_build_time),
        "is_preview": False,
    })


def set_envs(app_uuid, envs):
    """envs: list of (key, value, is_build_time). Returns (True, None) or (None, error)."""
    for key, value, is_build_time in envs:
        _, error = set_env(app_uuid, key, value, is_build_time=is_build_time)
        if error:
            return None, f"env {key}: {error}"
    return True, None


def add_persistent_storage(app_uuid, mount_path, name):
    """Add a persistent volume so a dealer's data survives redeploys. POST
    /applications/{uuid}/storages (Coolify v4). Best-effort — the caller treats a failure as a
    warning, not a hard stop, since the endpoint/fields are the most version-sensitive here."""
    return _request("POST", f"/applications/{app_uuid}/storages", {
        "name": name,
        "mount_path": mount_path,
    })


def deploy(app_uuid):
    """Trigger a deploy. GET /deploy?uuid={uuid}. Returns (data, error)."""
    return _request("GET", f"/deploy?uuid={app_uuid}", None)


def get_application(app_uuid):
    """Fetch an app (for status). GET /applications/{uuid}."""
    return _request("GET", f"/applications/{app_uuid}", None)


# ---------------------------------------------------------------------------------------------
# Naming helpers — one place that turns a dealer slug into names + public URLs.
# ---------------------------------------------------------------------------------------------

def api_domain(slug):
    return f"https://{slug}-api.{config()['domain_base']}"


def frontend_domain(slug):
    return f"https://{slug}.{config()['domain_base']}"
