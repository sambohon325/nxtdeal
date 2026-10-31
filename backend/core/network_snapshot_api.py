"""
ACL layer for the anonymous network snapshot route (2026-07-16). Matches
backend/core/*_api.py's usual "validate + call the real function + shape the response"
convention, just with a shared-secret check in place of the usual employee-token check
-- this route is called by the NXTDeal Hub server-to-server, not by a logged-in
employee's browser, so there's no Authorization: Bearer <token> to verify here.

DEALEROS_NETWORK_KEY must be explicitly configured with a nonpublic key of at
least 32 characters. Missing/default keys disable network access in every mode;
the rest of the application may continue serving staff. Per-tenant credentials
remain migration work. The shared checker protects reads and Hub control writes.
"""

import hmac

from core.network_snapshot import build_anonymous_snapshot
from core.pii_scan import PiiDetectedError
from core.secrets import get_secret

_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"
_DEV_FALLBACK_KEY = "dev-only-insecure-network-key-change-me"


def check_network_key(provided_key):
    """Returns None if valid, or an error dict if not -- matches this codebase's
    existing convention of returning {"error": ...} rather than raising, so the caller
    (api/app.py's route handler) decides the HTTP status."""

    expected = get_secret(_NETWORK_KEY_ENV_VAR, "")
    valid_configuration = (
        isinstance(expected, str) and len(expected.strip()) >= 32
        and not expected.strip().startswith("dev-only-")
    )
    if not valid_configuration or not isinstance(provided_key, str):
        return {"error": "invalid or missing X-NXTDeal-Network-Key"}
    try:
        matches = hmac.compare_digest(provided_key.encode("utf-8"), expected.encode("utf-8"))
    except UnicodeError:
        matches = False
    if not matches:
        return {"error": "invalid or missing X-NXTDeal-Network-Key"}

    return None


def get_anonymous_snapshot_api(network_key):

    error = check_network_key(network_key)

    if error:
        return error

    try:
        return build_anonymous_snapshot()
    except PiiDetectedError as exc:
        # A real, intentional block (core/pii_scan.py's Task #10 pre-flight check),
        # surfaced as a clean {"error": ...} response matching this codebase's
        # established convention -- not an unhandled exception producing a generic
        # FastAPI 500. Deliberately omits each finding's own value_excerpt here:
        # returning the actual flagged text back out over this same route would defeat
        # the entire point of blocking it in the first place. Only the finding TYPE,
        # confidence, and structural path (e.g. "root.departments.sales.some_kpi.label")
        # are surfaced -- enough for a developer to locate and fix the real leak without
        # ever transmitting the leaked content itself.
        return {
            "error": "network snapshot blocked: potential PII detected",
            "findings": [
                {"type": f["type"], "confidence": f["confidence"], "path": f["path"]}
                for f in exc.findings
            ],
        }
