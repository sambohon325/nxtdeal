"""
core/shared_knowledge.py — Pillar 5: ONE shared AI knowledge for the agent fleet
(2026-07-23). Sam's fifth architectural pillar: "all agents read and write one shared
knowledge, all actions on the graph."

The substrate for this was already true after Pillars 3 and 4:
  * Pillar 3 verified the single-graph invariant (tests/test_single_graph_invariant.py) —
    there is exactly ONE ledger / graph.json, no side store.
  * Pillar 4's fleet (core/bot_fleet.py) already records every team's real workflow steps
    (TeamWorkflowEvent) and mines each team's RECURRING workflows — all in that one graph.

But each team agent still read ONLY its own section (get_team_workflows(section) is
siloed). So the knowledge existed in one graph, yet no agent could benefit from what
another agent had learned. This module closes that gap: it is the SHARED read/write layer
over the fleet's knowledge, so every team agent draws from — and contributes to — a single
pool the whole fleet sees.

Two honest kinds of shared knowledge, no fabrication:
  * WORKFLOW entries — a team's RECOGNIZED recurring workflow (already ≥ MIN_WORKFLOW_
    OCCURRENCES real, observed occurrences in core/bot_fleet) promoted into the shared pool
    so other agents can see how that team works. Published explicitly (an auditable admin
    action), upserted by a stable signature so re-publishing updates rather than duplicates.
  * INSIGHT entries — a free-form learning a team member (or the admin) writes for the whole
    fleet to read. The direct analogue of core/bot_learning.py recording a real signal:
    knowledge exists only because someone explicitly contributed it.

On top of the persisted pool, read_shared_knowledge() also surfaces a LIVE cross-team
analysis — cross_team_workflows() — which action-sequences 2+ teams have independently
recognized RIGHT NOW. That is the genuinely shared knowledge: a pattern multiple teams do,
computed from live recognitions (not fabricated, not a model — the same explainable count
core/bot_fleet already exposes), so an agent always sees what the rest of the fleet has in
common even before anything is published.

Every entry is an ordinary SharedKnowledgeEntry in the same single ledger as everything
else (see core/entity_types.py / the one-graph invariant) — never a separate store.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import SHARED_KNOWLEDGE_ENTRY
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.bot_fleet import (
    FLEET_SECTIONS,
    normalize_section,
    get_team_workflows,
    _display,
)

KIND_WORKFLOW = "workflow"
KIND_INSIGHT = "insight"
VALID_KINDS = (KIND_WORKFLOW, KIND_INSIGHT)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _signature(kind, section, steps=None, title=None):
    """A stable dedup key so re-publishing the same recognized workflow, or re-contributing
    the same-titled insight, UPDATES the one entry instead of piling up duplicates. This is
    what keeps the shared pool a single coherent knowledge base rather than an append log."""

    if kind == KIND_WORKFLOW:
        return "workflow:" + section + ":" + ">".join(steps or [])
    return "insight:" + section + ":" + (title or "").strip().lower()


def _all_entries():
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == SHARED_KNOWLEDGE_ENTRY
    ]


def _find_by_signature(signature):
    for entity in _all_entries():
        if entity.attributes.get("signature") == signature:
            return entity
    return None


def _serialize(entity):
    a = entity.attributes
    return {
        "id": entity.id,
        "kind": a.get("kind"),
        "source_section": a.get("source_section"),
        "source_display": _display(a["source_section"]) if a.get("source_section") else None,
        "title": a.get("title"),
        "body": a.get("body"),
        "steps": a.get("steps") or [],
        "occurrences": a.get("occurrences"),
        "contributor": a.get("contributor"),
        "contributed_at": a.get("contributed_at"),
        "updated_at": a.get("updated_at"),
    }


# ------------------------------------------------------------------------------------
# WRITE — contribute to the one shared pool.
# ------------------------------------------------------------------------------------

def _upsert(kind, section, contributor, *, title=None, body=None, steps=None,
            occurrences=None, persist=True):
    """Create the entry, or update the existing one with the same signature. Returns
    (entry_dict, created_bool)."""

    signature = _signature(kind, section, steps=steps, title=title)
    existing = _find_by_signature(signature)
    now = _now()

    if existing is not None:
        existing.attributes.update({
            "title": title,
            "body": body,
            "steps": steps,
            "occurrences": occurrences,
            "contributor": contributor,
            "updated_at": now,
        })
        if persist:
            save_graph(GRAPH_PATH)
        return _serialize(existing), False

    entry = Entity(
        id=id_generator.generate("SKE"),
        entity_type=SHARED_KNOWLEDGE_ENTRY,
        attributes={
            "kind": kind,
            "source_section": section,
            "title": title,
            "body": body,
            "steps": steps,
            "occurrences": occurrences,
            "contributor": contributor,
            "signature": signature,
            "contributed_at": now,
            "updated_at": now,
        },
    )
    ledger.add_entity(entry)
    if persist:
        save_graph(GRAPH_PATH)
    return _serialize(entry), True


def contribute_insight(section, contributor, title, body):
    """A team member (or admin) writes a free-form learning into the shared pool for the
    whole fleet to read. Analogue of core/bot_learning.py recording a real signal — the
    knowledge exists only because someone explicitly contributed it."""

    section = normalize_section(section)
    if section is None:
        return {"error": "Unknown section -- must be one of the nine NXTDeal teams"}

    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        return {"error": "An insight needs a title"}
    if not body:
        return {"error": "An insight needs a body"}

    entry, created = _upsert(
        KIND_INSIGHT, section, contributor, title=title, body=body,
    )

    audit_log.record(
        event_type="shared_knowledge_contributed",
        summary=f"{contributor} {'added' if created else 'updated'} a shared insight "
                f"'{title}' from the {_display(section)} team",
        entity_id=entry["id"],
        actor=contributor,
        details={"section": section, "kind": KIND_INSIGHT, "created": created},
    )

    return {"entry": entry, "created": created}


def publish_recognized_workflows(publisher_id):
    """Promote every team's currently-recognized recurring workflows into the shared pool,
    so each agent's learning becomes visible to the whole fleet. Idempotent: upserts by
    signature, so running it repeatedly refreshes occurrence counts rather than duplicating.
    An explicit, auditable ADMIN action — nothing is auto-fabricated."""

    published = 0
    updated = 0
    sections_touched = []

    for section in FLEET_SECTIONS:
        team = get_team_workflows(section)
        if not team.get("available"):
            continue
        recognized = team.get("recognized_workflows") or []
        if recognized:
            sections_touched.append(section)
        for wf in recognized:
            _, created = _upsert(
                KIND_WORKFLOW,
                section,
                f"agent:{section}",
                title=" → ".join(wf["steps"]),
                steps=wf["steps"],
                occurrences=wf["occurrences"],
                persist=False,
            )
            if created:
                published += 1
            else:
                updated += 1

    # One persist for the whole bulk operation (the ledger is serialized whole).
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="shared_knowledge_published",
        summary=f"{publisher_id} published fleet workflows to shared knowledge "
                f"({published} new, {updated} refreshed)",
        entity_id=None,
        actor=publisher_id,
        details={
            "published": published,
            "updated": updated,
            "sections": sections_touched,
        },
    )

    return {
        "published": published,
        "updated": updated,
        "sections": sections_touched,
        "total_entries": len(_all_entries()),
    }


def delete_entry(entry_id, admin_id):
    """Admin curation of the shared pool. Removes one entry from the single graph."""

    entity = ledger.get_all().get(entry_id)
    if entity is None or entity.entity_type != SHARED_KNOWLEDGE_ENTRY:
        return {"error": "No such shared-knowledge entry"}

    title = entity.attributes.get("title")
    del ledger.entities[entry_id]
    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="shared_knowledge_deleted",
        summary=f"{admin_id} removed shared-knowledge entry '{title}'",
        entity_id=entry_id,
        actor=admin_id,
        details={"entry_id": entry_id},
    )

    return {"deleted": entry_id}


# ------------------------------------------------------------------------------------
# READ — the one shared knowledge every agent draws from.
# ------------------------------------------------------------------------------------

def cross_team_workflows():
    """LIVE shared knowledge: which recognized action-sequences 2+ teams have INDEPENDENTLY
    recognized right now. Computed from live recognitions in core/bot_fleet (no persistence
    needed, always current) — a real, explainable count of a pattern multiple teams do, the
    clearest expression of knowledge the fleet holds in common."""

    seq_to_sections = {}
    for section in FLEET_SECTIONS:
        team = get_team_workflows(section)
        if not team.get("available"):
            continue
        for wf in team.get("recognized_workflows") or []:
            key = tuple(wf["steps"])
            seq_to_sections.setdefault(key, {})[section] = wf["occurrences"]

    shared = []
    for steps, sections in seq_to_sections.items():
        if len(sections) >= 2:
            shared.append({
                "steps": list(steps),
                "length": len(steps),
                "teams": sorted(sections.keys()),
                "team_count": len(sections),
                "total_occurrences": sum(sections.values()),
            })

    shared.sort(key=lambda s: (s["team_count"], s["total_occurrences"]), reverse=True)
    return shared


def read_shared_knowledge(for_section=None):
    """The one shared pool, as any team agent (or person) sees it. Returns every persisted
    entry plus the live cross-team analysis. If `for_section` is given, additionally splits
    the pool into this team's own contributions vs. what it can learn FROM THE REST OF THE
    FLEET — the whole point of the pillar."""

    entries = [_serialize(e) for e in _all_entries()]
    entries.sort(key=lambda e: e.get("updated_at") or "", reverse=True)

    result = {
        "entries": entries,
        "entry_count": len(entries),
        "cross_team_workflows": cross_team_workflows(),
        "note": (
            "One shared knowledge pool for the whole agent fleet — every team agent reads "
            "from and writes to it, all on the single graph (Pillar 3). Workflow entries are "
            "real recurring workflows recognized by a team; insights are explicitly "
            "contributed; cross-team workflows are patterns 2+ teams independently recognized."
        ),
    }

    norm = normalize_section(for_section) if for_section else None
    if norm:
        result["for_section"] = norm
        result["for_display"] = _display(norm)
        result["own"] = [e for e in entries if e["source_section"] == norm]
        result["from_other_teams"] = [e for e in entries if e["source_section"] != norm]

    return result


def knowledge_summary():
    """Fleet-wide transparency counts for the shared pool."""

    entries = _all_entries()
    per_section = {}
    kinds = {KIND_WORKFLOW: 0, KIND_INSIGHT: 0}

    for e in entries:
        section = e.attributes.get("source_section")
        per_section[section] = per_section.get(section, 0) + 1
        kind = e.attributes.get("kind")
        if kind in kinds:
            kinds[kind] += 1

    return {
        "total_entries": len(entries),
        "workflow_entries": kinds[KIND_WORKFLOW],
        "insight_entries": kinds[KIND_INSIGHT],
        "contributing_sections": sorted(k for k in per_section if k),
        "entries_per_section": per_section,
        "cross_team_pattern_count": len(cross_team_workflows()),
    }
