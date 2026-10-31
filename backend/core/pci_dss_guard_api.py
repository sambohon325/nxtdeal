"""
ACL layer for the PCI-DSS posture self-check (security-hardening Task #11, half 1 of
2). Matches core/lending_compliance_api.py's "validate role + call the real function"
convention exactly.

The blocking pre-flight check itself (assert_no_card_data(), wired into
core/payments.py's record_payment()) needs no ACL layer of its own -- it's not a
route, it's an internal guard every caller of record_payment() already passes through
regardless of role, same as core/pii_scan.py's assert_no_pii() call inside
core/network_snapshot.py's build_anonymous_snapshot().

Only the on-demand, dealership-wide posture SCAN is exposed as a real route, and that
one does need a role gate -- it's a compliance-officer-facing self-check, not
something every employee should be able to trigger.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.pci_dss_guard import run_pci_posture_scan

_COMPLIANCE_OFFICER_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to the PCI-DSS posture scan with your current "
             "role -- Admin, Operations, or Finance can run it."
}


def run_pci_posture_scan_api(role):

    if role not in _COMPLIANCE_OFFICER_ROLES:
        return _FORBIDDEN

    return run_pci_posture_scan()
