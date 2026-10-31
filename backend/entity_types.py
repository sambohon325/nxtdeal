"""
This module used to be a byte-for-byte duplicate of core/entity_types.py (found during
cleanup 2026-07-13 — see BUILD_QUEUE.md). core/entity_types.py is the one core/permissions.py
and everything else actually imports from, so it's the canonical copy now. This file is
kept as a re-export only in case anything still does `from entity_types import X` — nothing
found in a repo-wide search did, but re-exporting is a free safety net vs. deleting outright.
"""

from core.entity_types import *  # noqa: F401,F403
