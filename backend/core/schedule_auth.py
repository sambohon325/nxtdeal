"""Worker token authentication for machine scheduling endpoints.

Each worker (desktop, mac, vps) gets a unique token stored in its own Hermes
.env file — never committed to git, never printed in logs. The server stores
only the SHA-256 hash, so a compromised graph dump can't recover live tokens.

Tokens are Bearer tokens scoped to schedule operations only. They authenticate
POST /programming-schedule/claim, POST /programming-schedule/runs/{run_id}/heartbeat,
and POST /programming-schedule/runs/{run_id}/complete — never human-facing routes.
"""
import hashlib
import json
import os
import secrets

from core.storage_paths import storage_path

WORKERS = ("desktop", "mac", "vps")
_TOKENS_FILE = storage_path("schedule_worker_tokens.json")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_hashes() -> dict[str, str]:
    if not os.path.exists(_TOKENS_FILE):
        return {}
    with open(_TOKENS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_hashes(hashes: dict[str, str]) -> None:
    parent = os.path.dirname(_TOKENS_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(hashes, f, indent=2)


def generate_worker_token(worker: str) -> str:
    """Generate a new token for *worker*. Returns the raw token — only this call
    shows it; subsequent calls return the existing hash for verification.

    The caller is responsible for putting the token in the target worker's
    .env (HERMES_SCHEDULE_TOKEN) and never logging it.
    """
    if worker not in WORKERS:
        raise ValueError(f"Unknown worker '{worker}'. Valid: {list(WORKERS)}")
    token = secrets.token_urlsafe(32)
    hashes = _load_hashes()
    hashes[worker] = _hash_token(token)
    _save_hashes(hashes)
    return token


def verify_worker_token(authorization: str | None) -> str | None:
    """Extract and verify a Bearer token. Returns the worker name or None.

    Uses secrets.compare_digest for constant-time comparison.
    """
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw = parts[1]
    provided = _hash_token(raw)
    for worker, stored in _load_hashes().items():
        if secrets.compare_digest(provided, stored):
            return worker
    return None


def worker_token_or_error(authorization: str | None) -> tuple[str | None, dict | None]:
    """Auth helper returning (worker, None) on success or (None, error) on failure.

    Mirrors the _ps_admin_or_error tuple convention so route handlers can do:
        worker, error = worker_token_or_error(authorization)
        if error: return error
    """
    worker = verify_worker_token(authorization)
    if not worker:
        return None, {"error": "Invalid or missing worker token", "status_code": 401}
    return worker, None


def list_workers() -> list[str]:
    """Return workers that have tokens registered."""
    return [w for w in WORKERS if w in _load_hashes()]
