"""Fix: TypeScript *** type fix should be in_review (base files exist)."""
import os, sys

REPO_ROOT = "C:/Users/sambo/.codex/.chatgpt-projects/g-p-6abf15cc62508191acf06fc913cef344/desktop-api-release"
BACKEND = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(REPO_ROOT)

from core.dealeros import ledger
from core import programming_schedule as ps
from core.storage_paths import GRAPH_PATH
from core.storage import save_graph

ledger.load(GRAPH_PATH)

ps.set_status("PS-typescript--type-fix", "in_review")
ps.add_event("PS-typescript--type-fix", "reconciled", "hermes",
             "Phase 0 reconciliation: base files (aiConfig.ts, AiConfig.tsx) confirmed to exist. "
             "Resources reference :line offsets. Work notes describe *** replaced with string type in aiConfig.ts:76 and AiConfig.tsx:261.")

save_graph(GRAPH_PATH)
print("✓ Fixed: PS-typescript--type-fix -> in_review")
print(f"Events: {len(ps.get_events('PS-typescript--type-fix'))}")

# Print final Phase 0 summary
print("\nFinal Phase 0 status:")
for item in ps.list_items():
    if item["phase"] == "Phase 0":
        events = ps.get_events(item["id"])
        print(f"  {item['id']}: {item['status']} ({len(events)} events)")

ledger.reset()
