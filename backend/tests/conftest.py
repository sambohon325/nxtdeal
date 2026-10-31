"""
Session-wide pytest isolation, backend/.

Real, severe incident this file exists to prevent (2026-07-19, discovered mid-session
while working the CAF-00123 missing_test_coverage Code Auditor finding): running
`pytest tests/test_deals.py` overwrote the REAL, live, ~6,300-entity production
storage/graph.json with a 3-entity test fixture (CUST-1/VEH-1/DEAL-00037), because
test_deals.py's `no_real_audit_writes` fixture only monkeypatches save_audit_log --
nothing in that file (or, per a follow-up audit, in ANY existing backend/tests/*.py
file) ever redirects save_graph()/GRAPH_PATH away from the real, default `storage/`
directory. core/storage_paths.py's own GRAPH_PATH/AUDIT_PATH/CREDENTIALS_PATH
constants are computed ONCE, at import time, from the DEALEROS_STORAGE_DIR env var
(default "storage" -- today's one real dealer's real data) -- so any test that reaches
a real core/*.py mutating function (directly, or via its *_api.py wrapper) silently
persists real writes into the real production file the instant that module is first
imported anywhere in the test process, with no test having to do anything wrong
beyond simply not knowing this file's own default applies to it too.

Recovered via the real Disaster Recovery playbook (a timestamped backup,
storage/backups/graph_20260718_045731.json -- the most recent one on disk; a
git-tracked historical commit was also available but slightly staler) -- but that
recovery is itself lossy: any real, live graph mutation made between that backup's
timestamp and the moment of corruption is genuinely gone, not reconstructible. See
CLAUDE.md's own incident write-up for the full account, including why this was not
fully recoverable.

The fix: set DEALEROS_STORAGE_DIR to a fresh, throwaway temp directory at COLLECTION
TIME -- before pytest imports any test module, and therefore before any test module's
own `from core...import ...` chain can trigger core/storage_paths.py's one-time,
import-time GRAPH_PATH/AUDIT_PATH/CREDENTIALS_PATH computation. Every test process,
regardless of which test file runs or what it imports, now resolves those three
paths to a private, disposable directory that is fully isolated from the real
dealer's live data -- structurally, not by convention, and not dependent on every
individual test file remembering to mock the right thing. Existing per-file fixtures
like test_deals.py's `no_real_audit_writes` (which prevents a real audit_log.json
disk write mid-suite even within the isolated temp dir, since core/audit.py's
audit_log singleton also persists on save) are additive belt-and-suspenders on top
of this, not a substitute for it -- keep them, but this file is what makes the whole
suite safe even for a test file that forgets to add one.
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime as _original_datetime
import datetime as _dt_module

import pytest


# On Windows, datetime.now() has ~15ms resolution. Entities created in rapid
# succession (two api_keys.generate_api_key calls back-to-back, etc.) get
# identical timestamps, making stable-sort order non-deterministic and causing
# sorting tests to flake. _MonotonicDatetime adds an incrementing microsecond
# delta so every now() call returns a strictly later timestamp.
_monotonic_counter = [0]


class _MonotonicDatetimeMeta(type):
    """Make isinstance(real_datetime, _MonotonicDatetime) True.

    bridge_credentials.py validates grants with isinstance(expires_at, datetime)
    where datetime is the module-level reference. After we replace that
    reference with _MonotonicDatetime, real datetime.datetime instances
    created elsewhere would fail the isinstance check (a parent instance is
    not a subclass instance), causing spurious CredentialUnavailable. The
    metaclass redirects __instancecheck__ back to the real datetime class.
    """
    def __instancecheck__(cls, instance):
        return isinstance(instance, _original_datetime)


class _MonotonicDatetime(_original_datetime, metaclass=_MonotonicDatetimeMeta):
    @classmethod
    def now(cls, tz=None):
        _monotonic_counter[0] += 1
        return _original_datetime.now(tz) + _dt_module.timedelta(
            microseconds=_monotonic_counter[0]
        )


# Executed once, at collection time, before pytest imports ANY test module in this
# directory (or any core/*.py module a test module might import) -- this is what makes
# the isolation structural rather than convention-based. A fresh directory per pytest
# invocation; nothing here is meant to be inspected after the run, so it's safe to
# just let the OS clean it up eventually if the rmtree below ever fails to run (e.g. a
# hard interrupt mid-suite).
_TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="dealeros_pytest_storage_")
os.environ["DEALEROS_STORAGE_DIR"] = _TEST_STORAGE_DIR

# api/app.py calls load_graph(GRAPH_PATH) unconditionally at module import time (not
# lazily, not inside a try/except) -- core/storage.py's load_graph() has no tolerance
# for a missing file (unlike load_audit_log()/load_credentials(), which both already
# degrade gracefully to an empty state on FileNotFoundError). Any test file that ends
# up importing api.app (directly, or transitively -- e.g. tests/test_route_protection.py
# imports helpers straight out of it) needs a real, valid, empty graph.json to already
# exist in the isolated temp dir before that import happens. Seed all three boot-critical
# files here for the same reason -- valid-but-empty, matching each module's own real
# save_*() output shape exactly, not a guess at the format.
with open(os.path.join(_TEST_STORAGE_DIR, "graph.json"), "w", encoding="utf-8") as _f:
    json.dump({"entities": [], "relationships": []}, _f)
with open(os.path.join(_TEST_STORAGE_DIR, "audit.json"), "w", encoding="utf-8") as _f:
    json.dump([], _f)
with open(os.path.join(_TEST_STORAGE_DIR, "credentials.json"), "w", encoding="utf-8") as _f:
    json.dump({}, _f)


@pytest.fixture(scope="session", autouse=True)
def _isolated_storage_dir_guard():
    """A hard, fail-loud guard (not just documentation) confirming the isolation
    above actually took effect for this process -- if core/storage_paths.py is ever
    refactored to stop reading DEALEROS_STORAGE_DIR at import time, or a test file
    somehow imports it before this conftest.py runs, this fails the whole session
    immediately with a clear message instead of silently writing to the real
    storage/ directory again."""

    from core.storage_paths import GRAPH_PATH

    assert GRAPH_PATH.startswith(_TEST_STORAGE_DIR), (
        f"SAFETY: core.storage_paths.GRAPH_PATH ('{GRAPH_PATH}') did not resolve "
        f"into this test session's isolated temp directory ('{_TEST_STORAGE_DIR}'). "
        f"Refusing to continue -- running the suite like this risks silently "
        f"overwriting the real, live storage/graph.json again (see this file's own "
        f"module docstring for the real incident that made this guard necessary)."
    )

    yield

    shutil.rmtree(_TEST_STORAGE_DIR, ignore_errors=True)


@pytest.fixture(autouse=True, scope="session")
def _patch_datetime_for_sort_stability():
    """Patch every imported core module's datetime reference so now() returns
    strictly increasing timestamps -- fixes sort-order flakiness on Windows
    (datetime.now() has ~15ms resolution; entities created in the same
    window get identical timestamps and stable-sort order is non-deterministic).

    Only core.* modules are patched. Third-party libraries (e.g. cryptography's
    Rust bindings) perform C-level type checks during isinstance/argument
    extraction that bypass Python metaclass __instancecheck__, so patching
    their datetime reference would break them with TypeError.
    """

    for _mod in list(sys.modules.values()):
        if _mod is None:
            continue
        mod_name = getattr(_mod, "__name__", "")
        if not mod_name.startswith("core."):
            continue
        if getattr(_mod, "datetime", None) is _original_datetime:
            _mod.datetime = _MonotonicDatetime
    yield


@pytest.fixture(autouse=True)
def _reset_monotonic_timestamp_counter():
    """Reset the monotonic counter before each test so deltas stay tiny."""
    _monotonic_counter[0] = 0
    yield
