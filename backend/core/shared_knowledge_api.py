"""
core/shared_knowledge_api.py — role-gated API layer for the fleet's shared AI knowledge
(2026-07-23, Pillar 5). Same split every *_api.py module follows: api/app.py imports these
thin wrappers, which apply the role gate and delegate to core/shared_knowledge.py.

Gate posture mirrors the fleet (core/bot_fleet_api.py):
  * READING the shared pool is open to any authenticated role — read-only operational
    insight, the same reasoning the fleet's get_team_workflows view uses.
  * CONTRIBUTING an insight is open to any authenticated employee — it's their real
    knowledge for the fleet, the direct analogue of recording a workflow step.
  * PUBLISHING recognized workflows into the pool and DELETING an entry are ADMIN-only —
    a fleet-wide management / curation action, exactly like activating an agent.
"""

from core.permissions import ADMIN
from core.shared_knowledge import (
    read_shared_knowledge,
    knowledge_summary,
    contribute_insight,
    publish_recognized_workflows,
    delete_entry,
)


def get_shared_knowledge_api(role, section=None):
    return {
        "knowledge": read_shared_knowledge(for_section=section),
        "summary": knowledge_summary(),
    }


def contribute_insight_api(employee_id, section, title, body):
    return contribute_insight(section, employee_id, title, body)


def publish_recognized_workflows_api(admin_role, admin_id):
    if admin_role != ADMIN:
        return {"error": "Admin role required to publish fleet workflows to shared knowledge"}
    return publish_recognized_workflows(admin_id)


def delete_shared_entry_api(admin_role, admin_id, entry_id):
    if admin_role != ADMIN:
        return {"error": "Admin role required to remove a shared-knowledge entry"}
    return delete_entry(entry_id, admin_id)
