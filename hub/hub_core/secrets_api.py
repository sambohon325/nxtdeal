"""
ACL layer for hub_core/secrets.py's posture report (security-hardening Task #13).

The Hub has no per-function role/ACL parameter convention at all -- confirmed via
this whole codebase's own Code Auditor findings review (CAF-00121's dismissal notes
state this plainly): the entire authorization boundary for every Hub route is the
single shared-secret X-NXTDeal-Hub-Key header, checked once at the route layer by
hub/app.py's own _check_hub_key(). This module therefore has no separate role gate
of its own -- it exists only so hub/app.py's own route handler has a single, named
function to call, matching every other hub_core/*_api.py module's shape.
"""

from hub_core.secrets import get_secrets_posture


def get_secrets_posture_api():
    return get_secrets_posture()
