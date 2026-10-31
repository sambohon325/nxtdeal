"""
ACL layer for core/secrets.py's posture report (security-hardening Task #13).

Matches the same narrow, security-posture-reporting gate this codebase already uses
for every comparable self-audit surface (core/crypto_agility_api.py,
core/pci_dss_guard.py's posture route, core/audit_center.py) -- ADMIN/OPERATIONS
only. Whether a given secret is currently on its insecure dev fallback is exactly the
kind of detail an attacker would want and a real admin needs -- it stays behind the
same gate as every other security self-check in this codebase, never broadly
viewable.

get_secret()/is_using_dev_fallback() themselves are NOT wrapped here -- they're the
real, low-level chokepoint every other core module should call directly (the same way
core/pii_scan.py's scan_for_pii()/assert_no_pii() are called directly by other core
modules without an _api.py layer in between); only the aggregate posture REPORT is
gated, since that's the one thing worth restricting who can see.
"""

from core.secrets import get_secrets_posture
from core.permissions import ADMIN, OPERATIONS

_VIEW_ROLES = (ADMIN, OPERATIONS)


def get_secrets_posture_api(role):
    if role not in _VIEW_ROLES:
        return {"error": "Admin/Operations role required to view secrets posture."}
    return get_secrets_posture()
