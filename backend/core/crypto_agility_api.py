"""
ACL layer for core/crypto_agility.py (security-hardening Task #12).

Matches the same narrow, security-posture-reporting gate this codebase already
uses for comparable self-audit surfaces -- core/audit_center.py,
core/ai_management.py, core/pci_dss_guard.py's own posture scan -- ADMIN/
OPERATIONS only. A cryptographic primitive inventory (even one that currently
reports "all clear") is the kind of detail that should stay behind the same
gate as every other security self-check in this codebase, not broadly
viewable.

versioned_digest()/verify_versioned_digest() themselves are NOT wrapped here --
they're stateless, pure functions with no graph access and no sensitive
disclosure of their own (a digest reveals nothing about what it's a digest
of), so any module that wants real algorithm agility for something it hashes
can import core.crypto_agility directly, the same way core/pii_scan.py's
scan_for_pii()/assert_no_pii() are called directly by other core modules
without going through an _api.py layer.
"""

from core.crypto_agility import get_crypto_agility_posture, run_crypto_inventory_scan
from core.permissions import ADMIN, OPERATIONS

_VIEW_ROLES = (ADMIN, OPERATIONS)


def get_crypto_agility_posture_api(role):
    if role not in _VIEW_ROLES:
        return {"error": "Admin/Operations role required to view the cryptographic agility posture."}
    return get_crypto_agility_posture()


def run_crypto_inventory_scan_api(role):
    if role not in _VIEW_ROLES:
        return {"error": "Admin/Operations role required to run the cryptographic inventory scan."}
    return run_crypto_inventory_scan()
