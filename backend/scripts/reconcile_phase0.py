"""Reconcile Phase 0 items: check if code exists, set to in_review."""
import os
import sys
import json

REPO_ROOT = "C:/Users/sambo/.codex/.chatgpt-projects/g-p-6abf15cc62508191acf06fc913cef344/desktop-api-release"
BACKEND = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND)

os.chdir(REPO_ROOT)

from core.dealeros import ledger
from core import programming_schedule as ps
from core.storage_paths import GRAPH_PATH
from core.storage import save_graph

# Load the seeded graph
ledger.load(GRAPH_PATH)
print(f"Loaded graph from: {GRAPH_PATH}")
items = ps.list_items()
print(f"Total items: {len(items)}")

# Reconcile Phase 0 items
phase0 = [i for i in items if i["phase"] == "Phase 0"]
print(f"\nReconciling Phase 0 ({len(phase0)} items):")
for item in phase0:
    title = item["title"]
    resources = item.get("resources", [])
    exists = []
    for res in resources:
        full_path = os.path.join(REPO_ROOT, res)
        exists.append((res, os.path.exists(full_path)))

    all_exist = all(e for _, e in exists) if exists else False
    new_status = "in_review" if all_exist else "blocked"

    ps.set_status(item["id"], new_status)
    evidence = (f"Phase 0 reconciliation: code exists={all_exist}, "
                f"files={[r for r, e in exists if e]}, "
                f"missing={[r for r, e in exists if not e]}")
    ps.add_event(item["id"], "reconciled", "hermes", evidence)
    print(f"  {item['id']}: {title} -> {new_status}")
    for r, e in exists:
        print(f"    {'[OK]' if e else '[MISSING]'} {r}")

save_graph(GRAPH_PATH)
print(f"\nGraph saved to: {GRAPH_PATH}")

# Verify
ledger.load(GRAPH_PATH)
reloaded = ps.list_items()
phase0_statuses = [(i["id"], i["status"]) for i in reloaded if i["phase"] == "Phase 0"]
print("\nPhase 0 statuses after reconciliation:")
for item_id, status in phase0_statuses:
    print(f"  {item_id}: {status}")

# Count events
for item in phase0:
    events = ps.get_events(item["id"])
    print(f"  Events for {item['id']}: {len(events)}")

ledger.reset()
