"""
Demo tenant self-seed (2026-07-25). On boot, if this is a DEALEROS_DEMO tenant and its graph
is empty, load the committed seed dataset (backend/seed_data/*.csv via run_seed_import) straight
into the in-memory ledger — ~5,700 entities: 500 vehicles, 500 customers, 1,000 leads, live
deals across every stage, service ROs, parts, campaigns, and a full employee roster.

Why this works cleanly: in a demo tenant every save_graph() is a no-op
(core.storage.demo_persistence_disabled), so the seed lands in memory only — nothing is written
to disk, nothing pollutes anything, and a redeploy/restart resets to the pristine seed. So the
demo boots fully populated (tours + AI Q&A have real data) with zero server file work and zero
persistence. On a real dealer backend the flag is off, so this is an immediate no-op.

Seeding adds ~2s to demo-tenant startup (measured); negligible and one-time per process.
"""

import contextlib
import io

from core.storage import demo_persistence_disabled
from core.dealeros import ledger


def ensure_seeded():
    """Idempotent: seeds only a demo tenant whose graph is empty. Returns a small status dict."""
    if not demo_persistence_disabled():
        return {"seeded": False, "reason": "not a demo tenant"}
    if len(ledger.get_all()) > 0:
        return {"seeded": False, "reason": "graph already populated"}

    try:
        import run_seed_import  # top-level module at backend/run_seed_import.py
        # Silence its progress prints (and its now-misleading "Saved to storage/graph.json"
        # line — saves are no-ops here); we log our own one-liner instead.
        with contextlib.redirect_stdout(io.StringIO()):
            run_seed_import.main()
    except Exception as error:  # never let a seed failure stop the demo tenant from booting
        print(f"WARNING: demo self-seed failed ({error}); the demo will start empty.")
        return {"seeded": False, "error": str(error)}

    count = len(ledger.get_all())
    print(f"DEMO: self-seeded {count} entities in memory (DEALEROS_DEMO — nothing persisted).")
    return {"seeded": True, "entities": count}
